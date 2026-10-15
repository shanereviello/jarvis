BEGIN;
SET ROLE jarvis_activity_owner;

CREATE TABLE IF NOT EXISTS activity.execution_requests (
    id uuid PRIMARY KEY,
    idempotency_key text NOT NULL UNIQUE,
    task_id uuid NOT NULL REFERENCES activity.tasks(id),
    operation text NOT NULL,
    workflow_template text NOT NULL,
    executor_profile text NOT NULL,
    normalized_contract jsonb NOT NULL,
    contract_sha256 text NOT NULL CHECK (contract_sha256 ~ '^[0-9a-f]{64}$'),
    current_state text NOT NULL,
    requested_by text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    validated_at timestamptz,
    claimed_at timestamptz,
    started_at timestamptz,
    finished_at timestamptz
);

CREATE TABLE IF NOT EXISTS activity.execution_approvals (
    id uuid PRIMARY KEY,
    execution_request_id uuid NOT NULL REFERENCES activity.execution_requests(id),
    approval_gate text NOT NULL,
    actor text NOT NULL,
    decision text NOT NULL CHECK (decision IN ('approved', 'rejected')),
    contract_sha256 text NOT NULL CHECK (contract_sha256 ~ '^[0-9a-f]{64}$'),
    idempotency_key text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (execution_request_id, approval_gate, idempotency_key)
);

CREATE TABLE IF NOT EXISTS activity.run_artifacts (
    id uuid PRIMARY KEY,
    execution_request_id uuid NOT NULL REFERENCES activity.execution_requests(id),
    run_id uuid REFERENCES activity.runs(id),
    artifact_type text NOT NULL,
    protected_absolute_path text NOT NULL CHECK (protected_absolute_path LIKE '/%'),
    sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
    media_type text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

ALTER TABLE activity.writer_leases
    ADD COLUMN IF NOT EXISTS execution_request_id uuid REFERENCES activity.execution_requests(id),
    ADD COLUMN IF NOT EXISTS run_id uuid REFERENCES activity.runs(id);

REVOKE ALL ON TABLE activity.execution_requests, activity.execution_approvals, activity.run_artifacts FROM PUBLIC;
REVOKE DELETE, TRUNCATE, REFERENCES, TRIGGER ON TABLE activity.execution_requests, activity.execution_approvals, activity.run_artifacts FROM jarvis_activity_app;
GRANT SELECT, INSERT, UPDATE ON activity.execution_requests TO jarvis_activity_app;
GRANT SELECT, INSERT ON activity.execution_approvals, activity.run_artifacts TO jarvis_activity_app;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON activity.writer_leases FROM jarvis_activity_app;
REVOKE SELECT ON activity.schema_migrations FROM jarvis_activity_app;

INSERT INTO activity.schema_migrations(version) VALUES (4)
ON CONFLICT (version) DO NOTHING;

RESET ROLE;
COMMIT;
