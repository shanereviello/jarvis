#!/usr/bin/env bash
set -Eeuo pipefail

MIGRATIONS_DIR="${1:-/migrations}"
fail() { printf 'migration executor error: %s\n' "$*" >&2; exit 1; }

shopt -s nullglob
paths=("$MIGRATIONS_DIR"/*)
(( ${#paths[@]} > 0 )) || fail "no migration files found in $MIGRATIONS_DIR"

declare -A migration_by_version=()
versions=()
for path in "${paths[@]}"; do
  [[ -f "$path" ]] || fail "non-file entry in migration directory: $path"
  basename=${path##*/}
  [[ "$basename" == "run_migrations.sh" ]] && continue
  if [[ ! "$basename" =~ ^([0-9]+)_[A-Za-z0-9._-]+\.sql$ ]]; then
    fail "malformed migration filename: $basename"
  fi
  version=$((10#${BASH_REMATCH[1]}))
  (( version > 0 )) || fail "migration version must be positive: $basename"
  if [[ -n "${migration_by_version[$version]+present}" ]]; then
    fail "duplicate migration version $version: ${migration_by_version[$version]} and $basename"
  fi
  migration_by_version[$version]="$path"
  versions+=("$version")
done

(( ${#versions[@]} > 0 )) || fail "no SQL migration files found in $MIGRATIONS_DIR"
mapfile -t ordered_versions < <(printf '%s\n' "${versions[@]}" | sort -n)
expected=1
for version in "${ordered_versions[@]}"; do
  if (( version != expected )); then
    fail "noncontiguous migration versions: expected $expected, found $version"
  fi
  ((expected += 1))
done

tracking_exists=$(psql -Atq -f - <<'SQL' | tr -d '[:space:]'
SET ROLE jarvis_activity_owner;
SELECT to_regclass('activity.schema_migrations') IS NOT NULL;
RESET ROLE;
SQL
)
[[ "$tracking_exists" == t || "$tracking_exists" == f ]] || fail "could not determine migration tracking table state"

recorded_count() {
  local version="$1"
  psql -v version="$version" -Atq -f - <<'SQL'
SET ROLE jarvis_activity_owner;
SELECT COUNT(*) FROM activity.schema_migrations WHERE version = :version;
RESET ROLE;
SQL
}

for version in "${ordered_versions[@]}"; do
  path=${migration_by_version[$version]}
  if [[ "$tracking_exists" == t ]]; then
    recorded=$(recorded_count "$version" | tr -d '[:space:]')
    [[ "$recorded" == 0 || "$recorded" == 1 ]] || fail "migration version $version has duplicate tracking rows"
    [[ "$recorded" == 1 ]] && continue
  elif (( version != 1 )); then
    fail "migration tracking table is absent before version $version"
  fi

  psql -v ON_ERROR_STOP=1 -f "$path"
  tracking_exists=t
  recorded=$(recorded_count "$version" | tr -d '[:space:]')
  [[ "$recorded" == 1 ]] || fail "migration $version completed without recording version $version"
done
