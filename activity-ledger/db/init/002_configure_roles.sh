#!/usr/bin/env bash
set -Eeuo pipefail

# PostgreSQL's init process runs this only during first database initialization.
# Values are read from Docker secrets and are never printed.
read_secret() { tr -d '\n' <"$1"; }
migrator_pw=$(read_secret /run/secrets/jarvis_activity_migrator_password)
app_pw=$(read_secret /run/secrets/jarvis_activity_app_password)
reader_pw=$(read_secret /run/secrets/jarvis_activity_reader_password)
backup_pw=$(read_secret /run/secrets/jarvis_activity_backup_password)
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --set=migrator_pw="$migrator_pw" --set=app_pw="$app_pw" \
  --set=reader_pw="$reader_pw" --set=backup_pw="$backup_pw" <<'SQL'
ALTER ROLE jarvis_activity_migrator LOGIN PASSWORD :'migrator_pw';
ALTER ROLE jarvis_activity_migrator LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE jarvis_activity_app LOGIN PASSWORD :'app_pw';
ALTER ROLE jarvis_activity_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE jarvis_activity_reader LOGIN PASSWORD :'reader_pw';
ALTER ROLE jarvis_activity_reader LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE jarvis_activity_backup LOGIN PASSWORD :'backup_pw';
ALTER ROLE jarvis_activity_backup LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE jarvis_activity_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
REVOKE jarvis_activity_owner FROM jarvis_activity_app, jarvis_activity_reader, jarvis_activity_backup;
GRANT jarvis_activity_owner TO jarvis_activity_migrator WITH INHERIT FALSE, SET TRUE;
GRANT CONNECT ON DATABASE jarvis_activity TO jarvis_activity_migrator, jarvis_activity_reader, jarvis_activity_backup;
GRANT USAGE ON SCHEMA activity TO jarvis_activity_reader, jarvis_activity_backup;
SQL
