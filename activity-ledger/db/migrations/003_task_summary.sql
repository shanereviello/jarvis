BEGIN;
SET ROLE jarvis_activity_owner;

CREATE OR REPLACE FUNCTION activity.get_task_summary(p_task_key text)
RETURNS TABLE (
    id uuid,
    task_key text,
    title text,
    description text,
    origin_type text,
    state text,
    created_at timestamptz,
    updated_at timestamptz,
    run_count bigint,
    active_writer_lease_count bigint
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, activity
AS $$
    SELECT
        t.id,
        t.task_key,
        t.title,
        t.description,
        t.origin_type,
        t.state,
        t.created_at,
        t.updated_at,
        (SELECT count(*) FROM activity.runs AS r WHERE r.task_id = t.id),
        (SELECT count(*) FROM activity.writer_leases AS wl
         WHERE wl.workspace_id = t.task_key AND wl.state = 'active')
    FROM activity.tasks AS t
    WHERE t.task_key = p_task_key
    LIMIT 1
$$;

REVOKE ALL ON FUNCTION activity.get_task_summary(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION activity.get_task_summary(text) TO jarvis_activity_app;

INSERT INTO activity.schema_migrations(version) VALUES (3)
ON CONFLICT (version) DO NOTHING;

RESET ROLE;
COMMIT;
