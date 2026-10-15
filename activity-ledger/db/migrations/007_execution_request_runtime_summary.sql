BEGIN;
SET ROLE jarvis_activity_owner;

CREATE FUNCTION activity.get_execution_request_runtime_summary(p_execution_request_id uuid)
RETURNS TABLE (
    execution_request_id uuid,
    associated_run_count bigint,
    associated_run_id uuid,
    run_status text,
    run_finished_at timestamptz,
    run_actor text,
    run_source_interface text,
    controller_lease_count bigint,
    active_controller_lease_count bigint,
    latest_controller_lease_state text,
    latest_controller_id text,
    latest_controller_attempt_number integer,
    latest_controller_released_at timestamptz,
    writer_lease_count bigint,
    active_writer_lease_count bigint
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, activity
AS $$
WITH run_summary AS (
    SELECT
        count(*)::bigint AS associated_run_count,
        CASE WHEN count(*) = 1 THEN (array_agg(activity.runs.id ORDER BY activity.runs.id))[1] END AS associated_run_id,
        CASE WHEN count(*) = 1 THEN (array_agg(activity.runs.status ORDER BY activity.runs.id))[1] END AS run_status,
        CASE WHEN count(*) = 1 THEN (array_agg(activity.runs.finished_at ORDER BY activity.runs.id))[1] END AS run_finished_at,
        CASE WHEN count(*) = 1 THEN (array_agg(activity.runs.actor ORDER BY activity.runs.id))[1] END AS run_actor,
        CASE WHEN count(*) = 1 THEN (array_agg(activity.runs.source_interface ORDER BY activity.runs.id))[1] END AS run_source_interface
    FROM activity.runs
    WHERE activity.runs.execution_request_id = p_execution_request_id
), controller_summary AS (
    SELECT
        count(*)::bigint AS controller_lease_count,
        count(*) FILTER (WHERE activity.execution_controller_leases.state = 'active')::bigint AS active_controller_lease_count
    FROM activity.execution_controller_leases
    WHERE activity.execution_controller_leases.execution_request_id = p_execution_request_id
), latest_controller_lease AS (
    SELECT
        activity.execution_controller_leases.state AS latest_controller_lease_state,
        activity.execution_controller_leases.controller_id AS latest_controller_id,
        activity.execution_controller_leases.attempt_number AS latest_controller_attempt_number,
        activity.execution_controller_leases.released_at AS latest_controller_released_at
    FROM activity.execution_controller_leases
    WHERE activity.execution_controller_leases.execution_request_id = p_execution_request_id
    ORDER BY activity.execution_controller_leases.claimed_at DESC, activity.execution_controller_leases.id DESC
    LIMIT 1
), writer_summary AS (
    SELECT
        count(*)::bigint AS writer_lease_count,
        count(*) FILTER (WHERE activity.writer_leases.state = 'active')::bigint AS active_writer_lease_count
    FROM activity.writer_leases
    WHERE activity.writer_leases.execution_request_id = p_execution_request_id
)
SELECT
    p_execution_request_id,
    run_summary.associated_run_count,
    run_summary.associated_run_id,
    run_summary.run_status,
    run_summary.run_finished_at,
    run_summary.run_actor,
    run_summary.run_source_interface,
    controller_summary.controller_lease_count,
    controller_summary.active_controller_lease_count,
    latest_controller_lease.latest_controller_lease_state,
    latest_controller_lease.latest_controller_id,
    latest_controller_lease.latest_controller_attempt_number,
    latest_controller_lease.latest_controller_released_at,
    writer_summary.writer_lease_count,
    writer_summary.active_writer_lease_count
FROM run_summary
CROSS JOIN controller_summary
CROSS JOIN writer_summary
LEFT JOIN latest_controller_lease ON true
WHERE EXISTS (
    SELECT 1
    FROM activity.execution_requests
    WHERE activity.execution_requests.id = p_execution_request_id
);
$$;

REVOKE ALL ON FUNCTION activity.get_execution_request_runtime_summary(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION activity.get_execution_request_runtime_summary(uuid) TO jarvis_activity_app;
REVOKE SELECT ON activity.schema_migrations FROM jarvis_activity_app;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON activity.writer_leases FROM jarvis_activity_app;

INSERT INTO activity.schema_migrations(version) VALUES (7)
ON CONFLICT (version) DO NOTHING;

RESET ROLE;
COMMIT;
