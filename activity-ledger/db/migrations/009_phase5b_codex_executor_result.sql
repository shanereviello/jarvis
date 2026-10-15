BEGIN;
SET ROLE jarvis_activity_owner;

CREATE UNIQUE INDEX phase5b_codex_executor_result_one_per_request
    ON activity.run_artifacts (execution_request_id)
    WHERE artifact_type = 'phase5b_codex_executor_result';

INSERT INTO activity.schema_migrations(version) VALUES (9)
ON CONFLICT (version) DO NOTHING;

RESET ROLE;
COMMIT;
