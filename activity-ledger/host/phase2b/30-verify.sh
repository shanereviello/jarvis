#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname "$0")/lib.sh"
require_host_repo
require_secrets_dir
require_secret jarvis_activity_migrator_password
require_secret jarvis_activity_app_password
require_secret jarvis_activity_reader_password
require_secret jarvis_activity_backup_password
require_secret controller_api_token
export JARVIS_ACTIVITY_MIGRATOR_PASSWORD_FILE="$(secret_file jarvis_activity_migrator_password)"
compose ps
compose config --services | grep -Fx "$POSTGRES_SERVICE"
compose config --services | grep -Fx "$MIGRATION_SERVICE"
compose config --services | grep -Fx "$ADAPTER_SERVICE"
compose exec -T "$POSTGRES_SERVICE" pg_isready -U jarvis_activity_migrator -d jarvis_activity
compose exec -T "$POSTGRES_SERVICE" sh -c 'export PGPASSWORD="$(cat /run/secrets/jarvis_activity_migrator_password)"; psql -U jarvis_activity_migrator -d jarvis_activity -v ON_ERROR_STOP=1 -c "SET ROLE jarvis_activity_owner" -c "SELECT version();" -c "SELECT version, applied_at FROM activity.schema_migrations ORDER BY version;" -c "\\dt activity.*" -c "\\di activity.*"'
migration_versions=$(compose exec -T "$POSTGRES_SERVICE" sh -c 'export PGPASSWORD="$(cat /run/secrets/jarvis_activity_migrator_password)"; psql -Atq -U jarvis_activity_migrator -d jarvis_activity -v ON_ERROR_STOP=1 -c "SET ROLE jarvis_activity_owner" -c "SELECT string_agg(version::text, chr(44) ORDER BY version) FROM activity.schema_migrations"' | tr -d '[:space:]')
[[ "$migration_versions" == "1,2,3,4,5,6,7,8,9,10" ]] || fail "expected migration versions 1,2,3,4,5,6,7,8,9,10; found $migration_versions"
index_inventory=$(compose exec -T "$POSTGRES_SERVICE" sh -c 'export PGPASSWORD="$(cat /run/secrets/jarvis_activity_migrator_password)"; psql -Atq -U jarvis_activity_migrator -d jarvis_activity -v ON_ERROR_STOP=1 -f -' <<'SQL' | tr -d '[:space:]'
SELECT string_agg(c.relname::text, chr(44) ORDER BY c.relname::text)
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'activity' AND c.relkind = 'i';
SQL
)
expected_indexes='events_pkey,events_run_id_idempotency_key_key,events_run_id_sequence_number_key,execution_approvals_execution_request_id_approval_gate_idem_key,execution_approvals_pkey,execution_controller_commands_pkey,execution_controller_commands_request_idempotency_key,execution_controller_commands_request_lookup,execution_controller_leases_expiration_lookup,execution_controller_leases_id_request_key,execution_controller_leases_one_active_request,execution_controller_leases_pkey,execution_controller_leases_request_attempt_key,execution_controller_leases_request_lookup,execution_request_events_idempotency_key,execution_request_events_pkey,execution_request_events_sequence_key,execution_requests_idempotency_key_key,execution_requests_pkey,git_workspaces_allocation_idempotency_key_key,git_workspaces_task_branch_key,git_workspaces_pkey,git_workspaces_repository_lookup,git_workspaces_task_key,git_workspaces_worktree_path_key,phase4b_fake_result_one_per_request,phase5a_model_free_result_one_per_request,phase5b_codex_executor_result_one_per_request,repository_registrations_canonical_path_key,repository_registrations_pkey,run_artifacts_pkey,run_artifacts_request_idempotency_key,runs_one_execution_request,runs_pkey,schema_migrations_pkey,tasks_pkey,tasks_task_key_key,writer_leases_pkey'
[[ "$index_inventory" == "$expected_indexes" ]] || fail "index inventory mismatch: $index_inventory"
table_inventory=$(compose exec -T "$POSTGRES_SERVICE" sh -c 'export PGPASSWORD="$(cat /run/secrets/jarvis_activity_migrator_password)"; psql -Atq -U jarvis_activity_migrator -d jarvis_activity -v ON_ERROR_STOP=1 -f -' <<'SQL' | tr -d '[:space:]'
SELECT string_agg(c.relname::text, chr(44) ORDER BY c.relname::text)
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'activity' AND c.relkind IN ('r', 'p');
SQL
)
expected_tables='events,execution_approvals,execution_controller_commands,execution_controller_leases,execution_request_events,execution_requests,git_workspaces,repository_registrations,run_artifacts,runs,schema_migrations,tasks,writer_leases'
[[ "$table_inventory" == "$expected_tables" ]] || fail "table inventory mismatch: $table_inventory"
foreign_key_inventory=$(compose exec -T "$POSTGRES_SERVICE" sh -c 'export PGPASSWORD="$(cat /run/secrets/jarvis_activity_migrator_password)"; psql -Atq -U jarvis_activity_migrator -d jarvis_activity -v ON_ERROR_STOP=1 -f -' <<'SQL' | tr -d '[:space:]'
SELECT string_agg(c.conname::text, chr(44) ORDER BY c.conname::text)
FROM pg_constraint c
JOIN pg_namespace n ON n.oid = c.connamespace
WHERE n.nspname = 'activity' AND c.contype = 'f';
SQL
)
expected_foreign_keys='events_run_id_fkey,execution_approvals_execution_request_id_fkey,execution_controller_commands_execution_request_id_fkey,execution_controller_commands_lease_request_fkey,execution_controller_leases_execution_request_id_fkey,execution_request_events_execution_request_id_fkey,execution_requests_task_id_fkey,git_workspaces_repository_registration_id_fkey,git_workspaces_task_id_fkey,run_artifacts_execution_request_id_fkey,run_artifacts_run_id_fkey,runs_execution_request_id_fkey,runs_task_id_fkey,writer_leases_execution_request_id_fkey,writer_leases_run_id_fkey'
[[ "$foreign_key_inventory" == "$expected_foreign_keys" ]] || fail "foreign-key inventory mismatch: $foreign_key_inventory"
role_audit=$(compose exec -T "$POSTGRES_SERVICE" sh -c 'export PGPASSWORD="$(cat /run/secrets/jarvis_activity_migrator_password)"; psql -Atq -U jarvis_activity_migrator -d jarvis_activity -v ON_ERROR_STOP=1 -f -' <<'SQL'
SELECT 'elevated=' || COALESCE(string_agg(rolname::text, chr(44) ORDER BY rolname::text), '')
FROM pg_roles
WHERE rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication OR rolbypassrls;
SELECT 'admin_bad=' || count(*) FROM pg_roles
WHERE rolname = 'jarvis_activity_admin'
  AND NOT (rolcanlogin AND rolsuper AND rolcreaterole AND rolcreatedb AND rolreplication AND rolbypassrls);
SELECT 'owner_bad=' || count(*) FROM pg_roles
WHERE rolname = 'jarvis_activity_owner'
  AND (rolcanlogin OR rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication OR rolbypassrls);
SELECT 'functional_bad=' || count(*) FROM pg_roles
WHERE rolname IN ('jarvis_activity_migrator', 'jarvis_activity_app', 'jarvis_activity_reader', 'jarvis_activity_backup')
  AND (NOT rolcanlogin OR rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication OR rolbypassrls);
SELECT 'membership_bad=' || count(*)
FROM pg_auth_members membership
JOIN pg_roles parent ON parent.oid = membership.roleid
JOIN pg_roles member ON member.oid = membership.member
WHERE parent.rolname = 'jarvis_activity_owner'
  AND (member.rolname <> 'jarvis_activity_migrator'
       OR membership.inherit_option IS NOT FALSE
       OR membership.set_option IS NOT TRUE);
SELECT 'unexpected_membership=' || count(*)
FROM pg_auth_members membership
JOIN pg_roles parent ON parent.oid = membership.roleid
JOIN pg_roles member ON member.oid = membership.member
WHERE parent.rolname = 'jarvis_activity_owner'
  AND member.rolname IN ('jarvis_activity_app', 'jarvis_activity_reader', 'jarvis_activity_backup', 'jarvis_activity_admin');
SQL
)
for expected in elevated=jarvis_activity_admin admin_bad=0 owner_bad=0 functional_bad=0 membership_bad=0 unexpected_membership=0; do
  grep -Fx "$expected" <<<"$role_audit" >/dev/null || fail "role audit failed: $expected"
done
function_attributes=$(compose exec -T "$POSTGRES_SERVICE" sh -c 'export PGPASSWORD="$(cat /run/secrets/jarvis_activity_migrator_password)"; psql -Atq -U jarvis_activity_migrator -d jarvis_activity -v ON_ERROR_STOP=1 -f -' <<'SQL'
SELECT 'function_security_definer=' || p.prosecdef
FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname = 'activity' AND p.proname = 'get_execution_request_runtime_summary';
SELECT 'function_language_sql=' || (l.lanname = 'sql')
FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace JOIN pg_language l ON l.oid = p.prolang
WHERE n.nspname = 'activity' AND p.proname = 'get_execution_request_runtime_summary';
SELECT 'function_stable=' || (p.provolatile = 's')
FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname = 'activity' AND p.proname = 'get_execution_request_runtime_summary';
SELECT 'function_fixed_search_path=' || (p.proconfig @> ARRAY['search_path=pg_catalog, activity'])
FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname = 'activity' AND p.proname = 'get_execution_request_runtime_summary';
SELECT 'function_owner=' || r.rolname
FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace JOIN pg_roles r ON r.oid = p.proowner
WHERE n.nspname = 'activity' AND p.proname = 'get_execution_request_runtime_summary';
SQL
)
for expected in function_security_definer=true function_language_sql=true function_stable=true function_fixed_search_path=true function_owner=jarvis_activity_owner; do
  grep -Fx "$expected" <<<"$function_attributes" >/dev/null || fail "runtime summary function assertion failed: $expected"
done
function_privileges=$(compose exec -T "$POSTGRES_SERVICE" sh -c 'export PGPASSWORD="$(cat /run/secrets/jarvis_activity_app_password)"; psql -Atq -U jarvis_activity_app -d jarvis_activity -v ON_ERROR_STOP=1 -f -' <<'SQL'
SELECT 'function_app_execute=' || has_function_privilege(current_user, 'activity.get_execution_request_runtime_summary(uuid)', 'EXECUTE');
SELECT 'function_public_execute=' || has_function_privilege('public', 'activity.get_execution_request_runtime_summary(uuid)', 'EXECUTE');
SELECT 'app_writer_select=' || has_table_privilege(current_user, 'activity.writer_leases', 'SELECT');
SQL
)
for expected in function_app_execute=true function_public_execute=false app_writer_select=false; do
  grep -Fx "$expected" <<<"$function_privileges" >/dev/null || fail "runtime summary privilege assertion failed: $expected"
done
printf '%s\n' '== role and grant assertions =='
compose exec -T "$POSTGRES_SERVICE" sh -c 'export PGPASSWORD="$(cat /run/secrets/jarvis_activity_reader_password)"; psql -U jarvis_activity_reader -d jarvis_activity -v ON_ERROR_STOP=1 -c "SELECT count(*) FROM activity.schema_migrations;" -c "SELECT count(*) FROM activity.writer_leases;"'
compose exec -T "$POSTGRES_SERVICE" sh -c 'export PGPASSWORD="$(cat /run/secrets/jarvis_activity_backup_password)"; psql -U jarvis_activity_backup -d jarvis_activity -v ON_ERROR_STOP=1 -c "SELECT count(*) FROM activity.schema_migrations;" -c "SELECT count(*) FROM activity.writer_leases;" -c "SELECT last_value FROM activity.events_id_seq;"'
assert_role_denied() {
  local role="$1" secret_path="$2" sql="$3" label="$4"
  if compose exec -T "$POSTGRES_SERVICE" sh -c 'export PGPASSWORD="$(cat "$1")"; psql -U "$2" -d jarvis_activity -v ON_ERROR_STOP=1 -c "$3"' -- "$secret_path" "$role" "$sql" >/dev/null 2>&1; then
    fail "$label unexpectedly succeeded for $role"
  fi
}
assert_role_denied jarvis_activity_app /run/secrets/jarvis_activity_app_password 'SELECT count(*) FROM activity.schema_migrations' 'app administrative-table read'
assert_role_denied jarvis_activity_reader /run/secrets/jarvis_activity_reader_password 'INSERT INTO activity.schema_migrations(version) VALUES (2147483647)' 'reader insert'
assert_role_denied jarvis_activity_reader /run/secrets/jarvis_activity_reader_password 'CREATE TABLE activity.phase2b_reader_should_fail(id integer)' 'reader create'
assert_role_denied jarvis_activity_backup /run/secrets/jarvis_activity_backup_password 'INSERT INTO activity.schema_migrations(version) VALUES (2147483646)' 'backup insert'
assert_role_denied jarvis_activity_backup /run/secrets/jarvis_activity_backup_password "UPDATE activity.writer_leases SET state='invalid'" 'backup update'
assert_role_denied jarvis_activity_backup /run/secrets/jarvis_activity_backup_password 'DELETE FROM activity.writer_leases' 'backup delete'
assert_role_denied jarvis_activity_backup /run/secrets/jarvis_activity_backup_password 'TRUNCATE activity.writer_leases' 'backup truncate'
assert_role_denied jarvis_activity_backup /run/secrets/jarvis_activity_backup_password 'CREATE TABLE activity.phase2b_backup_should_fail(id integer)' 'backup create'
assert_role_denied jarvis_activity_backup /run/secrets/jarvis_activity_backup_password 'ALTER TABLE activity.writer_leases ADD COLUMN phase2b_should_fail integer' 'backup alter'
app_privileges=$(compose exec -T "$POSTGRES_SERVICE" sh -c 'export PGPASSWORD="$(cat /run/secrets/jarvis_activity_app_password)"; psql -Atq -U jarvis_activity_app -d jarvis_activity -v ON_ERROR_STOP=1 -f -' <<'SQL'
SELECT 'events_select=' || has_table_privilege('jarvis_activity_app', 'activity.execution_request_events', 'SELECT');
SELECT 'events_insert=' || has_table_privilege('jarvis_activity_app', 'activity.execution_request_events', 'INSERT');
SELECT 'events_update=' || has_table_privilege('jarvis_activity_app', 'activity.execution_request_events', 'UPDATE');
SELECT 'events_delete=' || has_table_privilege('jarvis_activity_app', 'activity.execution_request_events', 'DELETE');
SELECT 'approvals_update=' || has_table_privilege('jarvis_activity_app', 'activity.execution_approvals', 'UPDATE');
SELECT 'approvals_delete=' || has_table_privilege('jarvis_activity_app', 'activity.execution_approvals', 'DELETE');
SELECT 'artifacts_update=' || has_table_privilege('jarvis_activity_app', 'activity.run_artifacts', 'UPDATE');
SELECT 'artifacts_delete=' || has_table_privilege('jarvis_activity_app', 'activity.run_artifacts', 'DELETE');
SELECT 'requests_update=' || has_table_privilege('jarvis_activity_app', 'activity.execution_requests', 'UPDATE');
SQL
)
for expected in events_select=true events_insert=true events_update=false events_delete=false approvals_update=false approvals_delete=false artifacts_update=false artifacts_delete=false requests_update=true; do
  grep -Fx "$expected" <<<"$app_privileges" >/dev/null || fail "app effective privilege assertion failed: $expected"
done
controller_privileges=$(compose exec -T "$POSTGRES_SERVICE" sh -c 'export PGPASSWORD="$(cat /run/secrets/jarvis_activity_app_password)"; psql -Atq -U jarvis_activity_app -d jarvis_activity -v ON_ERROR_STOP=1 -f -' <<'SQL'
SELECT 'leases_select=' || has_table_privilege('jarvis_activity_app', 'activity.execution_controller_leases', 'SELECT');
SELECT 'leases_insert=' || has_table_privilege('jarvis_activity_app', 'activity.execution_controller_leases', 'INSERT');
SELECT 'leases_update=' || has_table_privilege('jarvis_activity_app', 'activity.execution_controller_leases', 'UPDATE');
SELECT 'leases_delete=' || has_table_privilege('jarvis_activity_app', 'activity.execution_controller_leases', 'DELETE');
SELECT 'leases_truncate=' || has_table_privilege('jarvis_activity_app', 'activity.execution_controller_leases', 'TRUNCATE');
SELECT 'commands_select=' || has_table_privilege('jarvis_activity_app', 'activity.execution_controller_commands', 'SELECT');
SELECT 'commands_insert=' || has_table_privilege('jarvis_activity_app', 'activity.execution_controller_commands', 'INSERT');
SELECT 'commands_update=' || has_table_privilege('jarvis_activity_app', 'activity.execution_controller_commands', 'UPDATE');
SELECT 'commands_delete=' || has_table_privilege('jarvis_activity_app', 'activity.execution_controller_commands', 'DELETE');
SELECT 'commands_truncate=' || has_table_privilege('jarvis_activity_app', 'activity.execution_controller_commands', 'TRUNCATE');
SQL
)
for expected in leases_select=true leases_insert=true leases_update=true leases_delete=false leases_truncate=false commands_select=true commands_insert=true commands_update=false commands_delete=false commands_truncate=false; do
  grep -Fx "$expected" <<<"$controller_privileges" >/dev/null || fail "controller effective privilege assertion failed: $expected"
done
for role in reader backup; do
  role_privileges=$(compose exec -T "$POSTGRES_SERVICE" sh -c 'export PGPASSWORD="$(cat "$1")"; psql -Atq -U "$2" -d jarvis_activity -v ON_ERROR_STOP=1 -f -' -- "/run/secrets/jarvis_activity_${role}_password" "jarvis_activity_${role}" <<'SQL'
SELECT 'leases_select=' || has_table_privilege(current_user, 'activity.execution_controller_leases', 'SELECT');
SELECT 'leases_insert=' || has_table_privilege(current_user, 'activity.execution_controller_leases', 'INSERT');
SELECT 'leases_update=' || has_table_privilege(current_user, 'activity.execution_controller_leases', 'UPDATE');
SELECT 'leases_delete=' || has_table_privilege(current_user, 'activity.execution_controller_leases', 'DELETE');
SELECT 'commands_select=' || has_table_privilege(current_user, 'activity.execution_controller_commands', 'SELECT');
SELECT 'commands_insert=' || has_table_privilege(current_user, 'activity.execution_controller_commands', 'INSERT');
SELECT 'commands_update=' || has_table_privilege(current_user, 'activity.execution_controller_commands', 'UPDATE');
SELECT 'commands_delete=' || has_table_privilege(current_user, 'activity.execution_controller_commands', 'DELETE');
SQL
  )
  for expected in leases_select=true leases_insert=false leases_update=false leases_delete=false commands_select=true commands_insert=false commands_update=false commands_delete=false; do
    grep -Fx "$expected" <<<"$role_privileges" >/dev/null || fail "$role effective privilege assertion failed: $expected"
  done
done
compose exec -T "$ADAPTER_SERVICE" python -c 'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8080/healthz", timeout=5).read().decode())'
printf '%s\n' '== network and publication evidence =='
compose ps --format json
postgres_container_id=$(compose_container_id "$POSTGRES_SERVICE")
adapter_container_id=$(compose_container_id "$ADAPTER_SERVICE")
docker inspect --format '{{json .NetworkSettings.Networks}}' "$postgres_container_id"
docker inspect --format '{{json .NetworkSettings.Networks}}' "$adapter_container_id"
ss -ltn
printf '%s\n' 'VERIFY BASELINE PASS; inspect role/grant and adapter evidence in command output.'
