"""DB-monitor: програмний моніторинг роботи СУБД PostgreSQL.

Кожні SCRAPE_INTERVAL секунд виконує SQL-запити до системних представлень PostgreSQL
(pg_stat_activity, pg_stat_user_tables, pg_stat_statements, pg_locks) та до таблиць
AnalyticsSystem і віддає результати як метрики Prometheus на /metrics.

Доповнює стандартний postgres-exporter метриками рівня застосунку
(кількість подій, сесій, воронка) та "топ повільних запитів".
"""
import os
import time

import psycopg2
from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor
from prometheus_client import Gauge, Histogram, start_http_server

from common.obs import exit_on_sigterm, setup_logging, setup_tracing

SERVICE = "db-monitor"
log = setup_logging(SERVICE)
tracer = setup_tracing(SERVICE)
Psycopg2Instrumentor().instrument(skip_dep_check=True)  # psycopg2-binary
exit_on_sigterm()

DSN = os.getenv("DATABASE_DSN", "postgresql://postgres:postgres@postgres:5432/telemetry")
INTERVAL = int(os.getenv("SCRAPE_INTERVAL", "15"))

# --- метрики рівня застосунку
EVENTS_TOTAL = Gauge("app_events_total", "Загальна кількість подій у таблиці Events")
EVENTS_LAST_MIN = Gauge("app_events_last_minute", "Подій за останню хвилину", ["event_type"])
SESSIONS_5M = Gauge("app_active_sessions_5m", "Унікальні сесії за останні 5 хвилин")
COMPANIES = Gauge("app_companies_total", "Зареєстровані компанії")
TOP_ELEMENTS = Gauge("app_top_clicked_elements_10m", "Топ-10 елементів за кліками (10 хв)", ["element"])
TOP_PAGES = Gauge("app_top_pages_10m", "Топ-10 сторінок за переглядами (10 хв)", ["url"])

# --- метрики СУБД
TABLE_SIZE = Gauge("db_table_size_bytes", "Розмір таблиці разом з індексами", ["table"])
TABLE_ROWS = Gauge("db_table_live_rows", "Оцінка кількості живих рядків", ["table"])
DEAD_ROWS = Gauge("db_table_dead_rows", "Мертві рядки (потребують VACUUM)", ["table"])
SEQ_SCANS = Gauge("db_table_seq_scans", "Кількість послідовних сканувань таблиці", ["table"])
IDX_SCANS = Gauge("db_table_idx_scans", "Кількість індексних сканувань таблиці", ["table"])
CONNECTIONS = Gauge("db_connections", "З'єднання за станом", ["state"])
LONGEST_QUERY = Gauge("db_longest_running_query_seconds", "Найдовший активний запит")
LOCKS_WAITING = Gauge("db_locks_waiting", "Кількість очікуваних блокувань")
TOP_QUERIES_MEAN = Gauge("db_top_query_mean_ms",
                         "Середній час запитів із топ-10 за сумарним часом (pg_stat_statements)",
                         ["queryid", "query"])
TOP_QUERIES_CALLS = Gauge("db_top_query_calls", "Кількість викликів топ-запитів", ["queryid", "query"])
COLLECT_DURATION = Histogram("db_monitor_collect_seconds", "Час збору всіх метрик за один цикл")
UP = Gauge("db_monitor_up", "1 якщо останній збір успішний")


def fetch(cur, sql, args=None):
    cur.execute(sql, args)
    return cur.fetchall()


def set_labeled(gauge, rows):
    gauge.clear()  # прибираємо старі значення лейблів, яких вже немає в топі
    for label, value in rows:
        gauge.labels(str(label)[:60]).set(value)


def collect(conn):
    with tracer.start_as_current_span("db_monitor.collect"), COLLECT_DURATION.time(), conn.cursor() as cur:
        has_events = fetch(cur, "SELECT to_regclass('public.\"Events\"') IS NOT NULL")[0][0]
        if has_events:
            EVENTS_TOTAL.set(fetch(cur, 'SELECT count(*) FROM "Events"')[0][0])
            set_labeled(EVENTS_LAST_MIN, fetch(cur, '''
                SELECT "EventType", count(*) FROM "Events"
                WHERE "Timestamp" > now() - interval '1 minute'
                GROUP BY 1'''))
            SESSIONS_5M.set(fetch(cur, '''
                SELECT count(DISTINCT "SessionId") FROM "Events"
                WHERE "Timestamp" > now() - interval '5 minutes' ''')[0][0])
            set_labeled(TOP_ELEMENTS, fetch(cur, '''
                SELECT "ElementTag", count(*) FROM "Events"
                WHERE "EventType" = 'click' AND "Timestamp" > now() - interval '10 minutes'
                GROUP BY 1 ORDER BY 2 DESC LIMIT 10'''))
            set_labeled(TOP_PAGES, fetch(cur, '''
                SELECT "Url", count(*) FROM "Events"
                WHERE "EventType" = 'page_view' AND "Timestamp" > now() - interval '10 minutes'
                GROUP BY 1 ORDER BY 2 DESC LIMIT 10'''))
            COMPANIES.set(fetch(cur, 'SELECT count(*) FROM "Companies"')[0][0])

        tables = fetch(cur, '''
                SELECT relname, pg_total_relation_size(relid), n_live_tup, n_dead_tup,
                       seq_scan, coalesce(idx_scan, 0)
                FROM pg_stat_user_tables''')
        for gauge in (TABLE_SIZE, TABLE_ROWS, DEAD_ROWS, SEQ_SCANS, IDX_SCANS):
            gauge.clear()  # видалені таблиці не повинні лишатися в метриках
        for rel, size, live, dead, seq, idx in tables:
            TABLE_SIZE.labels(rel).set(size)
            TABLE_ROWS.labels(rel).set(live)
            DEAD_ROWS.labels(rel).set(dead)
            SEQ_SCANS.labels(rel).set(seq)
            IDX_SCANS.labels(rel).set(idx)

        set_labeled(CONNECTIONS, fetch(cur, '''
            SELECT coalesce(state, 'background'), count(*) FROM pg_stat_activity GROUP BY 1'''))
        LONGEST_QUERY.set(fetch(cur, '''
            SELECT coalesce(max(extract(epoch FROM now() - query_start)), 0)
            FROM pg_stat_activity WHERE state = 'active' AND pid <> pg_backend_pid()''')[0][0])
        LOCKS_WAITING.set(fetch(cur, "SELECT count(*) FROM pg_locks WHERE NOT granted")[0][0])

        if fetch(cur, "SELECT count(*) FROM pg_extension WHERE extname = 'pg_stat_statements'")[0][0]:
            # Лише DML: у них pg_stat_statements замінює значення на $1, $2 ...
            # Службові команди (CREATE ROLE ... PASSWORD '...') зберігаються дослівно і в метрики потрапити не повинні.
            rows = fetch(cur, '''
                SELECT queryid, regexp_replace(query, '\\s+', ' ', 'g'), mean_exec_time, calls
                FROM pg_stat_statements
                WHERE dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
                  AND query ~* '^\\s*(select|insert|update|delete|with)\\M'
                ORDER BY mean_exec_time * calls DESC LIMIT 10''')
            TOP_QUERIES_MEAN.clear()
            TOP_QUERIES_CALLS.clear()
            for qid, q, mean, calls in rows:
                TOP_QUERIES_MEAN.labels(str(qid), q[:80]).set(mean)
                TOP_QUERIES_CALLS.labels(str(qid), q[:80]).set(calls)


def main():
    start_http_server(int(os.getenv("METRICS_PORT", "8000")))
    conn = None
    while True:
        try:
            if conn is None or conn.closed:
                # таймаути: моніторинг не повинен зависати разом із проблемною БД
                conn = psycopg2.connect(DSN, connect_timeout=5, options="-c statement_timeout=10000")
                conn.autocommit = True
                log.info("Connected to PostgreSQL")
            collect(conn)
            UP.set(1)
        except Exception as e:  # будь-яка помилка збору не повинна зупиняти цикл моніторингу
            UP.set(0)
            log.error(f"Failed to collect DB metrics: {e!r}")
            try:
                conn and conn.close()
            except psycopg2.Error:
                pass
            conn = None
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
