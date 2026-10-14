#!/usr/bin/env bash
set -Eeuo pipefail

REPO="${JARVIS_PHASE2B_REPO:-/srv/hermes-dev/jarvis/tasks/TASK-20260916-001-central-codex-activity-prototype/repo}"
COMPOSE_FILE="$REPO/deploy/jarvis-activity/compose.yaml"
PROJECT="${JARVIS_PHASE2B_PROJECT:-jarvis-activity}"
SECRETS_DIR="${JARVIS_PHASE2B_SECRETS_DIR:-/srv/jarvis-activity/secrets}"
COMPOSE=(docker compose --project-name "$PROJECT" --file "$COMPOSE_FILE")
POSTGRES_SERVICE=jarvis-activity-postgres
ADAPTER_SERVICE=jarvis-activity-adapter
MIGRATION_SERVICE=jarvis-activity-migrate
RUNNER_SERVICE=runner

if [[ "${SUDO_UID:-}" =~ ^[0-9]+$ && "${SUDO_GID:-}" =~ ^[0-9]+$ ]]; then
  OPERATOR_UID="$SUDO_UID"
  OPERATOR_GID="$SUDO_GID"
else
  OPERATOR_UID="$(id -u)"
  OPERATOR_GID="$(id -g)"
fi
OPERATOR_OWNER="$OPERATOR_UID:$OPERATOR_GID"

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
require_host_repo() { [[ "$(hostname -s)" == "server01" ]] || fail "run this operation on server01, not inside Hermes"; [[ -d "$REPO/.git" ]] || fail "host repository not found: $REPO"; }
require_secrets_dir() { [[ -d "$SECRETS_DIR" ]] || fail "secret directory missing: $SECRETS_DIR (run 00-create-secrets.sh)"; }
compose() { "${COMPOSE[@]}" "$@"; }
compose_container_id() {
  local service="$1"
  shift
  local ids=()
  local id
  while IFS= read -r id; do
    [[ -n "$id" ]] && ids+=("$id")
  done < <(compose ps "$@" -q "$service")
  [[ "${#ids[@]}" -eq 1 ]] || fail "expected exactly one container ID for Compose service $service, found ${#ids[@]}"
  printf '%s\n' "${ids[0]}"
}
secret_file() { printf '%s/%s\n' "$SECRETS_DIR" "$1"; }
export JARVIS_ACTIVITY_BOOTSTRAP_PASSWORD_FILE="$SECRETS_DIR/postgres_bootstrap_password"
export JARVIS_ACTIVITY_MIGRATOR_PASSWORD_FILE="$SECRETS_DIR/jarvis_activity_migrator_password"
export JARVIS_ACTIVITY_APP_PASSWORD_FILE="$SECRETS_DIR/jarvis_activity_app_password"
export JARVIS_ACTIVITY_READER_PASSWORD_FILE="$SECRETS_DIR/jarvis_activity_reader_password"
export JARVIS_ACTIVITY_BACKUP_PASSWORD_FILE="$SECRETS_DIR/jarvis_activity_backup_password"
export JARVIS_ADAPTER_TOKEN_FILE="$SECRETS_DIR/adapter_api_token"
export JARVIS_CONTROLLER_TOKEN_FILE="$SECRETS_DIR/controller_api_token"
require_secret() { local p; p=$(secret_file "$1"); [[ -f "$p" && ! -L "$p" ]] || fail "secret must be a regular non-symlink file: $p"; [[ "$(stat -c '%a' "$p")" == 444 ]] || fail "secret must be mode 444: $p"; [[ "$(stat -c '%u:%g' "$p")" == "$OPERATOR_OWNER" ]] || fail "secret must be owned by the invoking operator: $p"; }
