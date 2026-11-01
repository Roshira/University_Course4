#!/bin/sh
# Виконується один раз при першому створенні БД (docker-entrypoint-initdb.d)
set -e
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" <<SQL
-- статистика виконання запитів (використовує db-monitor і дашборд "PostgreSQL")
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- окремий користувач лише для читання — ним Grafana напряму читає таблиці AnalyticsSystem
CREATE ROLE grafana_ro LOGIN PASSWORD '${GRAFANA_DB_PASSWORD}';
GRANT CONNECT ON DATABASE ${POSTGRES_DB} TO grafana_ro;
GRANT USAGE ON SCHEMA public TO grafana_ro;
-- таблиці створює EF Core-міграція пізніше, тому даємо права "на майбутнє"
ALTER DEFAULT PRIVILEGES FOR ROLE ${POSTGRES_USER} IN SCHEMA public GRANT SELECT ON TABLES TO grafana_ro;
GRANT pg_monitor TO grafana_ro;
SQL
