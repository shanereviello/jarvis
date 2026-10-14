BEGIN;
SET ROLE jarvis_activity_owner;

ALTER TABLE activity.execution_requests
    ADD CONSTRAINT execution_requests_operation_check
    CHECK (operation IN ('analyze', 'review', 'modify', 'verify'));

ALTER TABLE activity.execution_requests
    ADD CONSTRAINT execution_requests_current_state_check
    CHECK (current_state IN (
        'submitted', 'validated', 'awaiting_execution_approval', 'queued',
        'allocated', 'running', 'verifying', 'awaiting_review', 'approved',
        'rejected', 'cancelled', 'failed', 'closing', 'closed'
    ));

ALTER TABLE activity.execution_approvals
    ADD CONSTRAINT execution_approvals_approval_gate_check
    CHECK (approval_gate IN ('execution', 'review', 'commit', 'push', 'deploy', 'destructive'));

ALTER TABLE activity.runs
    ADD COLUMN execution_request_id uuid REFERENCES activity.execution_requests(id);

CREATE TABLE activity.execution_request_events (
    id uuid PRIMARY KEY,
    execution_request_id uuid NOT NULL REFERENCES activity.execution_requests(id),
    sequence_number integer NOT NULL CHECK (sequence_number > 0),
    idempotency_key text NOT NULL,
    event_type text NOT NULL,
    from_state text,
    to_state text NOT NULL,
    actor text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT execution_request_events_sequence_key
        UNIQUE (execution_request_id, sequence_number),
    CONSTRAINT execution_request_events_idempotency_key
        UNIQUE (execution_request_id, idempotency_key),
    CONSTRAINT execution_request_events_from_state_check
        CHECK (from_state IS NULL OR from_state IN (
            'submitted', 'validated', 'awaiting_execution_approval', 'queued',
            'allocated', 'running', 'verifying', 'awaiting_review', 'approved',
            'rejected', 'cancelled', 'failed', 'closing', 'closed'
        )),
    CONSTRAINT execution_request_events_to_state_check
        CHECK (to_state IN (
            'submitted', 'validated', 'awaiting_execution_approval', 'queued',
            'allocated', 'running', 'verifying', 'awaiting_review', 'approved',
            'rejected', 'cancelled', 'failed', 'closing', 'closed'
        ))
);

REVOKE ALL ON TABLE activity.execution_request_events FROM PUBLIC;
REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON activity.execution_request_events, activity.execution_approvals, activity.run_artifacts
    FROM jarvis_activity_app;
GRANT SELECT, INSERT
    ON activity.execution_request_events, activity.execution_approvals, activity.run_artifacts
    TO jarvis_activity_app;
GRANT SELECT ON activity.execution_request_events TO jarvis_activity_reader, jarvis_activity_backup;
REVOKE SELECT ON activity.schema_migrations FROM jarvis_activity_app;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON activity.writer_leases FROM jarvis_activity_app;

ALTER DEFAULT PRIVILEGES FOR ROLE jarvis_activity_owner IN SCHEMA activity
    REVOKE UPDATE, DELETE ON TABLES FROM jarvis_activity_app;

INSERT INTO activity.schema_migrations(version) VALUES (5)
ON CONFLICT (version) DO NOTHING;

RESET ROLE;
COMMIT;
