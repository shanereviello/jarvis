BEGIN;
SET ROLE jarvis_activity_owner;

-- Phase 5B executor classifications are persisted through the existing
-- controller failure command. Extend the earlier Phase 4A constraint
-- additively; controller_error and lease_expired remain valid too.
ALTER TABLE activity.execution_controller_leases
    DROP CONSTRAINT execution_controller_leases_failure_reason_check;
ALTER TABLE activity.execution_controller_leases
    ADD CONSTRAINT execution_controller_leases_failure_reason_check
    CHECK (failure_reason IS NULL OR failure_reason IN (
        'timeout', 'lease_expired', 'protocol_error', 'evidence_error', 'controller_error',
        'work_order_rejected', 'repository_binding_failed', 'instruction_validation_failed',
        'repository_policy_violation', 'model_timeout', 'model_error', 'malformed_model_response',
        'tool_limit_exceeded', 'output_limit_exceeded', 'validation_failed', 'validation_timeout',
        'git_policy_violation', 'git_commit_failed', 'evidence_generation_failed',
        'evidence_publication_failed', 'unsafe_worktree', 'unsafe_instruction',
        'replay_conflict', 'internal_error'
    ));

-- Additive Phase 5B durable bindings. This source migration is not executed by
-- this slice. Runtime writer stopping/reaping remains a Phase 5B.6 concern.
CREATE TABLE activity.phase5b_execution_bindings (
    execution_request_id uuid PRIMARY KEY REFERENCES activity.execution_requests(id),
    controller_lease_id uuid NOT NULL,
    run_id uuid NOT NULL REFERENCES activity.runs(id),
    allocation_id uuid NOT NULL REFERENCES activity.git_workspaces(allocation_id),
    work_order_sha256 text NOT NULL,
    work_order jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT phase5b_execution_bindings_controller_fkey
        FOREIGN KEY (controller_lease_id, execution_request_id)
        REFERENCES activity.execution_controller_leases(id, execution_request_id),
    CONSTRAINT phase5b_execution_bindings_work_order_hash_check
        CHECK (work_order_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT phase5b_execution_bindings_work_order_object_check
        CHECK (jsonb_typeof(work_order) = 'object')
);

CREATE TABLE activity.phase5b_execution_writer_leases (
    id uuid PRIMARY KEY,
    execution_request_id uuid NOT NULL REFERENCES activity.execution_requests(id),
    controller_lease_id uuid NOT NULL,
    run_id uuid NOT NULL REFERENCES activity.runs(id),
    allocation_id uuid NOT NULL REFERENCES activity.git_workspaces(allocation_id),
    worktree_id uuid NOT NULL,
    writer_id text NOT NULL,
    owner_id text NOT NULL,
    generation bigint NOT NULL,
    fence_sha256 text NOT NULL,
    state text NOT NULL,
    acquired_at timestamptz NOT NULL DEFAULT now(),
    lease_expires_at timestamptz NOT NULL,
    released_at timestamptz,
    CONSTRAINT phase5b_writer_leases_controller_fkey
        FOREIGN KEY (controller_lease_id, execution_request_id)
        REFERENCES activity.execution_controller_leases(id, execution_request_id),
    CONSTRAINT phase5b_writer_leases_fence_check
        CHECK (fence_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT phase5b_writer_leases_generation_check
        CHECK (generation > 0),
    CONSTRAINT phase5b_writer_leases_state_check
        CHECK (state IN ('active', 'released', 'expired', 'recovery_required')),
    CONSTRAINT phase5b_writer_leases_timestamp_check
        CHECK (lease_expires_at >= acquired_at AND (released_at IS NULL OR released_at >= acquired_at)),
    CONSTRAINT phase5b_writer_leases_identity_key
        UNIQUE (execution_request_id, run_id, allocation_id, writer_id)
);

CREATE UNIQUE INDEX phase5b_writer_leases_one_active_allocation
    ON activity.phase5b_execution_writer_leases (allocation_id)
    WHERE state = 'active';

CREATE INDEX phase5b_execution_bindings_run_lookup
    ON activity.phase5b_execution_bindings (run_id);
CREATE UNIQUE INDEX phase5b_codex_patch_one_per_request
    ON activity.run_artifacts (execution_request_id)
    WHERE artifact_type = 'phase5b_codex_patch';
CREATE INDEX phase5b_writer_leases_expiration_lookup
    ON activity.phase5b_execution_writer_leases (state, lease_expires_at);

REVOKE ALL ON TABLE activity.phase5b_execution_bindings, activity.phase5b_execution_writer_leases FROM PUBLIC;
GRANT SELECT, INSERT ON activity.phase5b_execution_bindings TO jarvis_activity_app;
GRANT SELECT, INSERT, UPDATE ON activity.phase5b_execution_writer_leases TO jarvis_activity_app;
GRANT SELECT ON activity.phase5b_execution_bindings, activity.phase5b_execution_writer_leases TO jarvis_activity_reader, jarvis_activity_backup;

INSERT INTO activity.schema_migrations(version) VALUES (11)
ON CONFLICT (version) DO NOTHING;

RESET ROLE;
COMMIT;
