BEGIN;
SET ROLE jarvis_activity_owner;

CREATE TABLE activity.execution_controller_leases (
    id uuid NOT NULL,
    execution_request_id uuid NOT NULL,
    controller_id text NOT NULL,
    attempt_number integer NOT NULL,
    claim_token_sha256 text NOT NULL,
    state text NOT NULL,
    claimed_at timestamptz NOT NULL DEFAULT now(),
    last_heartbeat_at timestamptz NOT NULL DEFAULT now(),
    lease_expires_at timestamptz NOT NULL,
    released_at timestamptz,
    failure_reason text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT execution_controller_leases_pkey PRIMARY KEY (id),
    CONSTRAINT execution_controller_leases_execution_request_id_fkey
        FOREIGN KEY (execution_request_id) REFERENCES activity.execution_requests(id),
    CONSTRAINT execution_controller_leases_controller_id_check
        CHECK (length(controller_id) BETWEEN 1 AND 128),
    CONSTRAINT execution_controller_leases_attempt_number_check
        CHECK (attempt_number > 0),
    CONSTRAINT execution_controller_leases_claim_token_sha256_check
        CHECK (claim_token_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT execution_controller_leases_state_check
        CHECK (state IN ('active', 'released', 'expired', 'failed')),
    CONSTRAINT execution_controller_leases_metadata_check
        CHECK (jsonb_typeof(metadata) = 'object' AND octet_length(metadata::text) <= 4096),
    CONSTRAINT execution_controller_leases_failure_reason_check
        CHECK (failure_reason IS NULL OR failure_reason IN ('timeout', 'lease_expired', 'protocol_error', 'evidence_error', 'controller_error')),
    CONSTRAINT execution_controller_leases_timestamp_state_check
        CHECK ((state = 'active' AND released_at IS NULL) OR (state <> 'active' AND released_at IS NOT NULL)),
    CONSTRAINT execution_controller_leases_timestamp_order_check
        CHECK (last_heartbeat_at >= claimed_at AND lease_expires_at >= claimed_at AND (released_at IS NULL OR released_at >= claimed_at)),
    CONSTRAINT execution_controller_leases_request_attempt_key
        UNIQUE (execution_request_id, attempt_number),
    CONSTRAINT execution_controller_leases_id_request_key
        UNIQUE (id, execution_request_id)
);

CREATE UNIQUE INDEX execution_controller_leases_one_active_request
    ON activity.execution_controller_leases (execution_request_id)
    WHERE state = 'active';
CREATE INDEX execution_controller_leases_request_lookup
    ON activity.execution_controller_leases (execution_request_id, attempt_number);
CREATE INDEX execution_controller_leases_expiration_lookup
    ON activity.execution_controller_leases (state, lease_expires_at);

CREATE TABLE activity.execution_controller_commands (
    id uuid NOT NULL,
    execution_request_id uuid NOT NULL,
    controller_lease_id uuid,
    actor text NOT NULL,
    controller_id text NOT NULL,
    command_type text NOT NULL,
    idempotency_key text NOT NULL,
    request_sha256 text NOT NULL,
    response_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT execution_controller_commands_pkey PRIMARY KEY (id),
    CONSTRAINT execution_controller_commands_execution_request_id_fkey
        FOREIGN KEY (execution_request_id) REFERENCES activity.execution_requests(id),
    CONSTRAINT execution_controller_commands_lease_request_fkey
        FOREIGN KEY (controller_lease_id, execution_request_id)
        REFERENCES activity.execution_controller_leases(id, execution_request_id),
    CONSTRAINT execution_controller_commands_actor_check
        CHECK (length(actor) BETWEEN 1 AND 128),
    CONSTRAINT execution_controller_commands_controller_id_check
        CHECK (length(controller_id) BETWEEN 1 AND 128),
    CONSTRAINT execution_controller_commands_type_check
        CHECK (command_type IN ('claim', 'heartbeat', 'running', 'verifying', 'evidence', 'finish', 'fail', 'recover_expired')),
    CONSTRAINT execution_controller_commands_idempotency_key_check
        CHECK (length(idempotency_key) BETWEEN 1 AND 256),
    CONSTRAINT execution_controller_commands_request_sha256_check
        CHECK (request_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT execution_controller_commands_response_metadata_check
        CHECK (jsonb_typeof(response_metadata) = 'object' AND octet_length(response_metadata::text) <= 4096),
    CONSTRAINT execution_controller_commands_request_idempotency_key
        UNIQUE (execution_request_id, idempotency_key)
);
CREATE INDEX execution_controller_commands_request_lookup
    ON activity.execution_controller_commands (execution_request_id, created_at);

REVOKE ALL ON TABLE activity.execution_controller_leases FROM PUBLIC;
REVOKE ALL ON TABLE activity.execution_controller_leases FROM jarvis_activity_app;
REVOKE ALL ON TABLE activity.execution_controller_leases FROM jarvis_activity_reader;
REVOKE ALL ON TABLE activity.execution_controller_leases FROM jarvis_activity_backup;
GRANT SELECT, INSERT, UPDATE ON activity.execution_controller_leases TO jarvis_activity_app;
GRANT SELECT ON activity.execution_controller_leases TO jarvis_activity_reader, jarvis_activity_backup;
REVOKE ALL ON TABLE activity.execution_controller_commands FROM PUBLIC;
REVOKE ALL ON TABLE activity.execution_controller_commands FROM jarvis_activity_app;
REVOKE ALL ON TABLE activity.execution_controller_commands FROM jarvis_activity_reader;
REVOKE ALL ON TABLE activity.execution_controller_commands FROM jarvis_activity_backup;
GRANT SELECT, INSERT ON activity.execution_controller_commands TO jarvis_activity_app;
GRANT SELECT ON activity.execution_controller_commands TO jarvis_activity_reader, jarvis_activity_backup;
REVOKE SELECT ON activity.schema_migrations FROM jarvis_activity_app;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON activity.writer_leases FROM jarvis_activity_app;
ALTER TABLE activity.run_artifacts ADD COLUMN idempotency_key text;
ALTER TABLE activity.run_artifacts ADD CONSTRAINT run_artifacts_idempotency_key_check CHECK (idempotency_key IS NULL OR length(idempotency_key) BETWEEN 1 AND 256);
CREATE UNIQUE INDEX run_artifacts_request_idempotency_key
    ON activity.run_artifacts (execution_request_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;
CREATE UNIQUE INDEX runs_one_execution_request
    ON activity.runs (execution_request_id)
    WHERE execution_request_id IS NOT NULL;
CREATE UNIQUE INDEX phase4b_fake_result_one_per_request
    ON activity.run_artifacts (execution_request_id)
    WHERE artifact_type = 'phase4b_fake_controller_result';

INSERT INTO activity.schema_migrations(version) VALUES (6)
ON CONFLICT (version) DO NOTHING;

RESET ROLE;
COMMIT;
