-- Apply only with the separately reviewed planning transport migration.
-- These grants cover the generated n8n intake, queue, and outbox operations.
-- Existing execution grants and other roles are deliberately untouched.
BEGIN;
GRANT SELECT, INSERT ON linear_bridge.codex_planning_sessions TO n8n_user;
GRANT SELECT, INSERT ON linear_bridge.codex_planning_deliveries TO n8n_user;
GRANT SELECT, INSERT, UPDATE ON linear_bridge.codex_planning_events TO n8n_user;
GRANT SELECT, INSERT, UPDATE ON linear_bridge.codex_planning_outbox TO n8n_user;
GRANT EXECUTE ON FUNCTION linear_bridge.codex_planning_accept(uuid,uuid,uuid,text,jsonb) TO n8n_user;
COMMIT;
