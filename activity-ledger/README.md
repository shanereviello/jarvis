# Activity ledger subproject

Imported from the independent central-codex-activity-prototype history. `db/migrations` is PostgreSQL schema source; top-level `migrations` supports retained SQLite compatibility tests. No schema migration has run during this import.

The running adapter still serves legacy phase4/phase5 endpoints. Preserve its modules/contracts until consumer audit allows removal. Operational Compose sources contain only database, adapter, and explicitly invoked migration service; inactive controller/executor/runner definitions were omitted. The phase5a override retains adapter compatibility mounts only. Old host/phase2b verification scripts are retained as test dependencies, not installed/run by this source import.

Historical SQL invariance is checked against SHA256s derived from original required commit 3d6433b; the old commit does not belong to canonical Jarvis history.
