-- Executed only by the isolated jarvis-activity Postgres container.
-- POSTGRES_USER is the dedicated bootstrap/break-glass admin.
ALTER ROLE jarvis_activity_admin LOGIN SUPERUSER CREATEDB CREATEROLE REPLICATION BYPASSRLS;

CREATE ROLE jarvis_activity_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE ROLE jarvis_activity_migrator NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE ROLE jarvis_activity_app NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE ROLE jarvis_activity_reader NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE ROLE jarvis_activity_backup NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;

GRANT CONNECT ON DATABASE jarvis_activity TO jarvis_activity_migrator, jarvis_activity_app, jarvis_activity_reader, jarvis_activity_backup;
CREATE SCHEMA IF NOT EXISTS activity AUTHORIZATION jarvis_activity_owner;
ALTER DATABASE jarvis_activity OWNER TO jarvis_activity_owner;
GRANT USAGE ON SCHEMA activity TO jarvis_activity_app, jarvis_activity_reader, jarvis_activity_backup;
