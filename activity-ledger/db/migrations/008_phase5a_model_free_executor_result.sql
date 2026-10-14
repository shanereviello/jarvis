BEGIN;
SET ROLE jarvis_activity_owner;

CREATE UNIQUE INDEX phase5a_model_free_result_one_per_request
    ON activity.run_artifacts (execution_request_id)
    WHERE artifact_type = 'phase5a_model_free_executor_result';

INSERT INTO activity.schema_migrations(version) VALUES (8)
ON CONFLICT (version) DO NOTHING;

RESET ROLE;
COMMIT;
