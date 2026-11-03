#!/bin/sh
# Виконується автоматично один раз при першому створенні БД (docker-entrypoint-initdb.d).
# Скрипт ідемпотентний: на вже існуючій БД його можна запустити повторно:
#   docker compose exec postgres sh /docker-entrypoint-initdb.d/10-init.sh
set -e
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
     -v db="$POSTGRES_DB" -v owner="$POSTGRES_USER" -v pw="$GRAFANA_DB_PASSWORD" <<'SQL'
-- статистика виконання запитів (використовують db-monitor і дашборд "PostgreSQL")
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- grafana_ro — користувач лише для читання: ним Grafana читає таблиці AnalyticsSystem,
-- а db-monitor і postgres-exporter — системну статистику (роль pg_monitor). Суперкористувач їм не потрібен.
SELECT 'CREATE ROLE grafana_ro LOGIN' WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'grafana_ro')
\gexec
-- пароль передається змінною psql, а не підставляється в текст SQL
ALTER ROLE grafana_ro PASSWORD :'pw';
GRANT CONNECT ON DATABASE :"db" TO grafana_ro;
GRANT USAGE ON SCHEMA public TO grafana_ro;
GRANT pg_monitor TO grafana_ro;
-- таблиці створює EF Core-міграція пізніше, тому даємо права "на майбутнє"
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner" IN SCHEMA public GRANT SELECT ON TABLES TO grafana_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO grafana_ro;

-- У таблиці "Companies" є Email і PasswordHash компаній — їх Grafana бачити не повинна.
-- Таблиця з'являється лише після міграції, тому права звужує event trigger після кожного CREATE/ALTER TABLE.
CREATE OR REPLACE FUNCTION restrict_grafana_ro() RETURNS event_trigger LANGUAGE plpgsql AS $$
BEGIN
    IF to_regclass('public."Companies"') IS NOT NULL THEN
        REVOKE SELECT ON public."Companies" FROM grafana_ro;
        GRANT SELECT ("Id", "AppId", "Name") ON public."Companies" TO grafana_ro;
    END IF;
END $$;
DROP EVENT TRIGGER IF EXISTS restrict_grafana_ro;
CREATE EVENT TRIGGER restrict_grafana_ro ON ddl_command_end
    WHEN TAG IN ('CREATE TABLE', 'ALTER TABLE')
    EXECUTE FUNCTION restrict_grafana_ro();
-- якщо таблиці вже існують (повторний запуск скрипта) — застосовуємо одразу
DO $$ BEGIN
    IF to_regclass('public."Companies"') IS NOT NULL THEN
        REVOKE SELECT ON public."Companies" FROM grafana_ro;
        GRANT SELECT ("Id", "AppId", "Name") ON public."Companies" TO grafana_ro;
    END IF;
END $$;
SQL
