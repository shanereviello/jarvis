# PostgreSQL activity ledger — retained compatibility boundary

This subproject preserves the deployed PostgreSQL adapter, schema, application-role contract and tests. The native engineering runner currently exports local evidence and does not use this adapter for task/worktree lifecycle.

The old SQLite simulation, duplicate durable controller and managed-root policy were retired. PostgreSQL execution compatibility remains because pg_adapter still imports those definitions and serves old routes. Remove that authority only after client audit and a tested minimal ledger/evidence replacement. Do not wire the new Hermes intake into the legacy controller endpoints.

`db/migrations` contains immutable PostgreSQL history; no production migrations/data changes occur in this PR. Operational Compose marks the migrator with explicit `migration` profile and starts the adapter after PostgreSQL health rather than running migrations automatically. Source definitions remain cutover candidates; the installed deployment is unchanged. `host/phase2b` is retained backup/restore/schema verification support, not a task executor.
