#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname "$0")/lib.sh"
require_host_repo
require_secrets_dir
require_secret jarvis_activity_migrator_password
require_secret jarvis_activity_backup_password
export JARVIS_ACTIVITY_MIGRATOR_PASSWORD_FILE="$(secret_file jarvis_activity_migrator_password)"
label=$(date -u +%Y%m%dT%H%M%SZ)
out="${JARVIS_PHASE2B_BACKUP_DIR:-/srv/jarvis-activity/backups}"
install -d -m 700 "$out"
file="$out/jarvis_activity-$label.dump"
checksum_file="$file.sha256"
restore_container="jarvis-activity-restore-$label"
dump_complete=0
cleanup() {
  local status=$?
  if [[ "$dump_complete" -eq 0 ]]; then
    rm -f -- "$file" "$checksum_file"
  fi
  docker rm -f "$restore_container" >/dev/null 2>&1 || true
  return "$status"
}
trap cleanup EXIT

source_counts=$(compose exec -T "$POSTGRES_SERVICE" sh -c 'export PGPASSWORD="$(cat /run/secrets/jarvis_activity_backup_password)"; psql -Atq -U jarvis_activity_backup -d jarvis_activity -v ON_ERROR_STOP=1 -f -' <<'SQL'
SELECT 'tasks=' || (SELECT count(*) FROM activity.tasks)
    || ',runs=' || (SELECT count(*) FROM activity.runs)
    || ',events=' || (SELECT count(*) FROM activity.events)
    || ',execution_requests=' || (SELECT count(*) FROM activity.execution_requests)
    || ',execution_approvals=' || (SELECT count(*) FROM activity.execution_approvals)
    || ',execution_request_events=' || (SELECT count(*) FROM activity.execution_request_events)
    || ',run_artifacts=' || (SELECT count(*) FROM activity.run_artifacts)
    || ',phase5a_artifacts=' || (SELECT count(*) FROM activity.run_artifacts WHERE artifact_type = 'phase5a_model_free_executor_result')
    || ',phase5b_artifacts=' || (SELECT count(*) FROM activity.run_artifacts WHERE artifact_type = 'phase5b_codex_executor_result')
    || ',execution_controller_commands=' || (SELECT count(*) FROM activity.execution_controller_commands)
    || ',execution_controller_leases=' || (SELECT count(*) FROM activity.execution_controller_leases)
    || ',repository_registrations=' || (SELECT count(*) FROM activity.repository_registrations)
    || ',git_workspaces=' || (SELECT count(*) FROM activity.git_workspaces)
    || ',writer_leases=' || (SELECT count(*) FROM activity.writer_leases);
SQL
)
source_counts=${source_counts//$'\r'/}
source_counts=${source_counts//$'\n'/}
[[ "$source_counts" =~ ^tasks=[0-9]+,runs=[0-9]+,events=[0-9]+,execution_requests=[0-9]+,execution_approvals=[0-9]+,execution_request_events=[0-9]+,run_artifacts=[0-9]+,phase5a_artifacts=[0-9]+,phase5b_artifacts=[0-9]+,execution_controller_commands=[0-9]+,execution_controller_leases=[0-9]+,repository_registrations=[0-9]+,git_workspaces=[0-9]+,writer_leases=[0-9]+$ ]] || fail "invalid source count output"

compose exec -T "$POSTGRES_SERVICE" sh -c 'export PGPASSWORD="$(cat /run/secrets/jarvis_activity_backup_password)"; pg_dump -U jarvis_activity_backup -d jarvis_activity --format=custom' >"$file"
chmod 600 "$file"
sha256sum "$file" >"$checksum_file"
sha256sum -c "$checksum_file"
dump_complete=1

docker run --detach --name "$restore_container" --network none \
  --env POSTGRES_DB=restore \
  --env POSTGRES_USER=restore_admin \
  --env POSTGRES_HOST_AUTH_METHOD=trust \
  --tmpfs /var/lib/postgresql/data \
  --volume "$out:/backup:ro" \
  postgres:16.4-bookworm >/dev/null
ready=0
for _ in {1..30}; do
  if docker exec "$restore_container" pg_isready -U restore_admin -d restore >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
done
[[ "$ready" -eq 1 ]] || fail 'disposable restore PostgreSQL did not become ready'
docker exec "$restore_container" pg_restore --no-owner --no-privileges -U restore_admin -d restore --exit-on-error "/backup/$(basename "$file")"
docker exec "$restore_container" psql -U restore_admin -d restore -v ON_ERROR_STOP=1 -c "DO \$\$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'jarvis_activity_app') THEN CREATE ROLE jarvis_activity_app NOLOGIN; END IF; END \$\$;" -c "REVOKE ALL ON FUNCTION activity.get_execution_request_runtime_summary(uuid) FROM PUBLIC;" -c "GRANT EXECUTE ON FUNCTION activity.get_execution_request_runtime_summary(uuid) TO jarvis_activity_app;"

restore_validation=$(docker exec -i "$restore_container" psql -Atq -U restore_admin -d restore -v ON_ERROR_STOP=1 -f - <<'SQL'
WITH expected(name) AS (
  VALUES ('events'), ('execution_approvals'), ('execution_request_events'),
         ('execution_requests'), ('git_workspaces'), ('repository_registrations'), ('run_artifacts'), ('execution_controller_commands'),
         ('execution_controller_leases'), ('runs'), ('schema_migrations'),
         ('tasks'), ('writer_leases')
), actual AS (
  SELECT c.relname::text AS name
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'activity' AND c.relkind IN ('r', 'p')
)
SELECT 'tables=' || CASE WHEN (SELECT array_agg(name ORDER BY name) FROM actual) = (SELECT array_agg(name ORDER BY name) FROM expected) THEN '1' ELSE '0' END;
WITH expected(name) AS (
  VALUES ('events_pkey'), ('events_run_id_idempotency_key_key'), ('events_run_id_sequence_number_key'),
         ('execution_approvals_execution_request_id_approval_gate_idem_key'), ('execution_approvals_pkey'),
         ('execution_request_events_idempotency_key'), ('execution_request_events_pkey'),
         ('execution_request_events_sequence_key'), ('execution_requests_idempotency_key_key'),
         ('execution_requests_pkey'), ('run_artifacts_pkey'), ('run_artifacts_request_idempotency_key'),
         ('execution_controller_commands_pkey'),
         ('execution_controller_commands_request_idempotency_key'), ('execution_controller_commands_request_lookup'),
         ('execution_controller_leases_pkey'), ('execution_controller_leases_request_attempt_key'),
         ('execution_controller_leases_id_request_key'), ('execution_controller_leases_one_active_request'),
         ('execution_controller_leases_request_lookup'), ('execution_controller_leases_expiration_lookup'),
         ('runs_pkey'), ('runs_one_execution_request'), ('phase4b_fake_result_one_per_request'), ('phase5a_model_free_result_one_per_request'), ('phase5b_codex_executor_result_one_per_request'), ('schema_migrations_pkey'),
         ('tasks_pkey'), ('tasks_task_key_key'), ('writer_leases_pkey'),
         ('git_workspaces_allocation_idempotency_key_key'), ('git_workspaces_task_branch_key'), ('git_workspaces_pkey'),
         ('git_workspaces_repository_lookup'), ('git_workspaces_task_key'), ('git_workspaces_worktree_path_key'),
         ('repository_registrations_canonical_path_key'), ('repository_registrations_pkey')
), actual AS (
  SELECT c.relname::text AS name
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'activity' AND c.relkind = 'i'
)
SELECT 'indexes=' || CASE WHEN (SELECT array_agg(name ORDER BY name) FROM actual) = (SELECT array_agg(name ORDER BY name) FROM expected) THEN '1' ELSE '0' END;
WITH expected(name) AS (
  VALUES ('events_run_id_fkey'), ('execution_approvals_execution_request_id_fkey'),
         ('execution_controller_commands_execution_request_id_fkey'), ('execution_controller_commands_lease_request_fkey'),
         ('execution_controller_leases_execution_request_id_fkey'), ('execution_request_events_execution_request_id_fkey'),
         ('execution_requests_task_id_fkey'), ('run_artifacts_execution_request_id_fkey'), ('run_artifacts_run_id_fkey'),
         ('runs_execution_request_id_fkey'), ('runs_task_id_fkey'), ('writer_leases_execution_request_id_fkey'),
         ('writer_leases_run_id_fkey'), ('git_workspaces_repository_registration_id_fkey'), ('git_workspaces_task_id_fkey')
), actual AS (
  SELECT c.conname::text AS name
  FROM pg_constraint c
  JOIN pg_namespace n ON n.oid = c.connamespace
  WHERE n.nspname = 'activity' AND c.contype = 'f'
)
SELECT 'foreign_keys=' || CASE WHEN (SELECT array_agg(name ORDER BY name) FROM actual) = (SELECT array_agg(name ORDER BY name) FROM expected) THEN '1' ELSE '0' END;
SELECT 'versions=' || COALESCE(string_agg(version::text, ',' ORDER BY version), '') FROM activity.schema_migrations;
SELECT 'function_security_definer=' || p.prosecdef
FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname = 'activity' AND p.proname = 'get_execution_request_runtime_summary';
SELECT 'function_fixed_search_path=' || (p.proconfig @> ARRAY['search_path=pg_catalog, activity'])
FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname = 'activity' AND p.proname = 'get_execution_request_runtime_summary';
SELECT 'function_public_execute=' || has_function_privilege('public', 'activity.get_execution_request_runtime_summary(uuid)', 'EXECUTE');
SELECT 'function_app_execute=' || has_function_privilege('jarvis_activity_app', 'activity.get_execution_request_runtime_summary(uuid)', 'EXECUTE');
SELECT 'counts=' || 'tasks=' || (SELECT count(*) FROM activity.tasks)
    || ',runs=' || (SELECT count(*) FROM activity.runs)
    || ',events=' || (SELECT count(*) FROM activity.events)
    || ',execution_requests=' || (SELECT count(*) FROM activity.execution_requests)
    || ',execution_approvals=' || (SELECT count(*) FROM activity.execution_approvals)
    || ',execution_request_events=' || (SELECT count(*) FROM activity.execution_request_events)
    || ',run_artifacts=' || (SELECT count(*) FROM activity.run_artifacts)
    || ',phase5a_artifacts=' || (SELECT count(*) FROM activity.run_artifacts WHERE artifact_type = 'phase5a_model_free_executor_result')
    || ',phase5b_artifacts=' || (SELECT count(*) FROM activity.run_artifacts WHERE artifact_type = 'phase5b_codex_executor_result')
    || ',execution_controller_commands=' || (SELECT count(*) FROM activity.execution_controller_commands)
    || ',execution_controller_leases=' || (SELECT count(*) FROM activity.execution_controller_leases)
    || ',repository_registrations=' || (SELECT count(*) FROM activity.repository_registrations)
    || ',git_workspaces=' || (SELECT count(*) FROM activity.git_workspaces)
    || ',writer_leases=' || (SELECT count(*) FROM activity.writer_leases);
SELECT 'referential_integrity=' || CASE WHEN
  NOT EXISTS (SELECT 1 FROM activity.runs r LEFT JOIN activity.tasks t ON t.id = r.task_id WHERE t.id IS NULL)
  AND NOT EXISTS (SELECT 1 FROM activity.runs r LEFT JOIN activity.execution_requests q ON q.id = r.execution_request_id WHERE r.execution_request_id IS NOT NULL AND q.id IS NULL)
  AND NOT EXISTS (SELECT 1 FROM activity.events e LEFT JOIN activity.runs r ON r.id = e.run_id WHERE r.id IS NULL)
  AND NOT EXISTS (SELECT 1 FROM activity.execution_requests q LEFT JOIN activity.tasks t ON t.id = q.task_id WHERE t.id IS NULL)
  AND NOT EXISTS (SELECT 1 FROM activity.execution_approvals a LEFT JOIN activity.execution_requests q ON q.id = a.execution_request_id WHERE q.id IS NULL)
  AND NOT EXISTS (SELECT 1 FROM activity.execution_request_events e LEFT JOIN activity.execution_requests q ON q.id = e.execution_request_id WHERE q.id IS NULL)
  AND NOT EXISTS (SELECT 1 FROM activity.run_artifacts a LEFT JOIN activity.execution_requests q ON q.id = a.execution_request_id WHERE q.id IS NULL)
  AND NOT EXISTS (SELECT 1 FROM activity.run_artifacts a LEFT JOIN activity.runs r ON r.id = a.run_id WHERE a.run_id IS NOT NULL AND r.id IS NULL)
  AND NOT EXISTS (SELECT 1 FROM activity.execution_controller_leases l LEFT JOIN activity.execution_requests q ON q.id = l.execution_request_id WHERE q.id IS NULL)
  AND NOT EXISTS (SELECT 1 FROM activity.execution_controller_commands c LEFT JOIN activity.execution_requests q ON q.id = c.execution_request_id WHERE q.id IS NULL)
  AND NOT EXISTS (SELECT 1 FROM activity.execution_controller_commands c LEFT JOIN activity.execution_controller_leases l ON l.id = c.controller_lease_id AND l.execution_request_id = c.execution_request_id WHERE c.controller_lease_id IS NOT NULL AND l.id IS NULL)
  AND NOT EXISTS (SELECT 1 FROM activity.writer_leases l LEFT JOIN activity.execution_requests q ON q.id = l.execution_request_id WHERE l.execution_request_id IS NOT NULL AND q.id IS NULL)
  AND NOT EXISTS (SELECT 1 FROM activity.writer_leases l LEFT JOIN activity.runs r ON r.id = l.run_id WHERE l.run_id IS NOT NULL AND r.id IS NULL)
  AND NOT EXISTS (SELECT 1 FROM activity.git_workspaces w LEFT JOIN activity.tasks t ON t.id = w.task_id WHERE t.id IS NULL)
  AND NOT EXISTS (SELECT 1 FROM activity.git_workspaces w LEFT JOIN activity.repository_registrations r ON r.repository_registration_id = w.repository_registration_id WHERE r.repository_registration_id IS NULL)
  THEN '1' ELSE '0' END;
SELECT 'lifecycle_request=' || count(*) FROM activity.execution_requests
 WHERE id = '03035190-31e8-4288-a127-bdac41de056c'
   AND contract_sha256 = 'b9600a850c4b677a10aedca6f5980fc3073fb341c58b71a1ddbff2733036e981'
   AND current_state = 'closed';
SELECT 'lifecycle_events=' || COALESCE(string_agg(sequence_number::text, ',' ORDER BY sequence_number), '')
 FROM activity.execution_request_events
 WHERE execution_request_id = '03035190-31e8-4288-a127-bdac41de056c';
SELECT 'lifecycle_approvals=' || count(*) FROM activity.execution_approvals
 WHERE execution_request_id = '03035190-31e8-4288-a127-bdac41de056c';
SELECT 'lifecycle_artifacts=' || count(*) FROM activity.run_artifacts
 WHERE execution_request_id = '03035190-31e8-4288-a127-bdac41de056c';
SELECT 'lifecycle_active_leases=' || count(*) FROM activity.writer_leases
 WHERE execution_request_id = '03035190-31e8-4288-a127-bdac41de056c' AND state = 'active';
SELECT 'lifecycle_runs=' || count(*) FROM activity.runs
 WHERE execution_request_id = '03035190-31e8-4288-a127-bdac41de056c';
SQL
)

expected_validation=(
  "tables=1"
  "indexes=1"
  "foreign_keys=1"
  "versions=1,2,3,4,5,6,7,8,9,10"
  "function_security_definer=true"
  "function_fixed_search_path=true"
  "function_public_execute=false"
  "function_app_execute=true"
  "counts=$source_counts"
  "referential_integrity=1"
  "lifecycle_request=1"
  "lifecycle_events=1,2,3,4,5,6,7"
  "lifecycle_approvals=1"
  "lifecycle_artifacts=0"
  "lifecycle_active_leases=0"
  "lifecycle_runs=0"
)
validation_failed=0
for expected in "${expected_validation[@]}"; do
  if ! grep -Fx "$expected" <<<"$restore_validation" >/dev/null; then
    validation_failed=1
  fi
done
if [[ "$validation_failed" -ne 0 ]]; then
  printf '%s\n' 'ISOLATED RESTORE VALIDATION OUTPUT:' >&2
  printf '%s\n' "$restore_validation" >&2
  fail 'isolated restore validation failed; complete safe output shown above'
fi
printf 'POSTGRES BACKUP/RESTORE PASS; disposable database cleanup is automatic.\n'
