BEGIN;
SET ROLE jarvis_activity_owner;

CREATE TABLE IF NOT EXISTS activity.schema_migrations (
    version integer PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS activity.tasks (
    id uuid PRIMARY KEY,
    task_key text NOT NULL UNIQUE CHECK (task_key ~ '^TASK-[0-9]{8}-[0-9]{3}$'),
    title text NOT NULL,
    description text NOT NULL,
    origin_type text NOT NULL,
    state text NOT NULL,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS activity.runs (
    id uuid PRIMARY KEY,
    task_id uuid NOT NULL REFERENCES activity.tasks(id),
    actor text NOT NULL,
    source_interface text NOT NULL,
    status text NOT NULL,
    started_at timestamptz NOT NULL,
    finished_at timestamptz
);

CREATE TABLE IF NOT EXISTS activity.events (
    id bigserial PRIMARY KEY,
    run_id uuid NOT NULL REFERENCES activity.runs(id),
    sequence_number integer NOT NULL CHECK (sequence_number > 0),
    idempotency_key text NOT NULL,
    event_type text NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL,
    UNIQUE (run_id, sequence_number),
    UNIQUE (run_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS activity.writer_leases (
    workspace_id text PRIMARY KEY,
    owner text NOT NULL,
    state text NOT NULL,
    acquired_at timestamptz NOT NULL
);

INSERT INTO activity.schema_migrations(version) VALUES (1)
ON CONFLICT (version) DO NOTHING;

REVOKE ALL ON ALL TABLES IN SCHEMA activity FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE ON activity.tasks, activity.runs, activity.events TO jarvis_activity_app;
GRANT USAGE, SELECT ON SEQUENCE activity.events_id_seq TO jarvis_activity_app;
GRANT SELECT ON activity.tasks, activity.runs, activity.events TO jarvis_activity_reader, jarvis_activity_backup;
GRANT DELETE ON activity.tasks, activity.runs, activity.events TO jarvis_activity_app;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA activity TO jarvis_activity_backup;
ALTER DEFAULT PRIVILEGES FOR ROLE jarvis_activity_owner IN SCHEMA activity GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO jarvis_activity_app;
ALTER DEFAULT PRIVILEGES FOR ROLE jarvis_activity_owner IN SCHEMA activity GRANT SELECT ON TABLES TO jarvis_activity_reader, jarvis_activity_backup;
ALTER DEFAULT PRIVILEGES FOR ROLE jarvis_activity_owner IN SCHEMA activity GRANT USAGE, SELECT ON SEQUENCES TO jarvis_activity_app;
ALTER DEFAULT PRIVILEGES FOR ROLE jarvis_activity_owner IN SCHEMA activity GRANT SELECT ON SEQUENCES TO jarvis_activity_backup;

RESET ROLE;
COMMIT;
