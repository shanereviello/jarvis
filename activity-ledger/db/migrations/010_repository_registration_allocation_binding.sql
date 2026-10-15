BEGIN;
SET ROLE jarvis_activity_owner;

CREATE TABLE activity.repository_registrations (
    repository_registration_id text PRIMARY KEY,
    canonical_path text NOT NULL UNIQUE,
    enabled boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT repository_registrations_id_check
        CHECK (repository_registration_id ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$'),
    CONSTRAINT repository_registrations_path_check
        CHECK (canonical_path LIKE '/%' AND canonical_path <> '/' AND canonical_path !~ '(^|/)\.\.?(/|$)'),
    CONSTRAINT repository_registrations_timestamp_order_check
        CHECK (updated_at >= created_at)
);

CREATE TABLE activity.git_workspaces (
    allocation_id uuid PRIMARY KEY,
    task_id uuid NOT NULL REFERENCES activity.tasks(id),
    repository_registration_id text NOT NULL REFERENCES activity.repository_registrations(repository_registration_id),
    worktree_path text NOT NULL UNIQUE,
    task_branch text NOT NULL UNIQUE,
    baseline_commit text NOT NULL,
    allocation_idempotency_key text NOT NULL UNIQUE,
    state text NOT NULL DEFAULT 'allocated',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT git_workspaces_path_check
        CHECK (worktree_path LIKE '/%' AND worktree_path <> '/' AND worktree_path !~ '(^|/)\.\.?(/|$)'),
    CONSTRAINT git_workspaces_branch_check
        CHECK (task_branch <> 'main' AND task_branch !~ '^/' AND task_branch !~ E'[\\x00-\\x1F]'),
    CONSTRAINT git_workspaces_baseline_commit_check
        CHECK (baseline_commit ~ '^[0-9a-f]{40}$'),
    CONSTRAINT git_workspaces_idempotency_key_check
        CHECK (allocation_idempotency_key ~ '^[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}$'),
    CONSTRAINT git_workspaces_state_check
        CHECK (state = 'allocated'),
    CONSTRAINT git_workspaces_timestamp_order_check
        CHECK (updated_at >= created_at),
    CONSTRAINT git_workspaces_task_key
        UNIQUE (task_id)
);

CREATE INDEX git_workspaces_repository_lookup
    ON activity.git_workspaces (repository_registration_id, task_id);

REVOKE ALL ON TABLE activity.repository_registrations FROM PUBLIC;
REVOKE ALL ON TABLE activity.git_workspaces FROM PUBLIC;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON activity.repository_registrations FROM jarvis_activity_app;
GRANT SELECT ON activity.repository_registrations TO jarvis_activity_app;
GRANT SELECT ON activity.repository_registrations TO jarvis_activity_reader, jarvis_activity_backup;
REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON activity.git_workspaces FROM jarvis_activity_app;
GRANT SELECT, INSERT ON activity.git_workspaces TO jarvis_activity_app;
GRANT SELECT ON activity.git_workspaces TO jarvis_activity_reader, jarvis_activity_backup;

INSERT INTO activity.schema_migrations(version) VALUES (10)
ON CONFLICT (version) DO NOTHING;

RESET ROLE;
COMMIT;
