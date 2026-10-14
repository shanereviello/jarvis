CREATE TABLE IF NOT EXISTS engineering_runs (id TEXT PRIMARY KEY, task_key TEXT NOT NULL, actor TEXT NOT NULL, source_interface TEXT NOT NULL, status TEXT NOT NULL, started_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS engineering_events (id INTEGER PRIMARY KEY, run_id TEXT NOT NULL, sequence_number INTEGER NOT NULL, event_type TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(run_id, sequence_number));
CREATE TABLE IF NOT EXISTS git_workspaces (id TEXT PRIMARY KEY, task_key TEXT NOT NULL, worktree_path TEXT NOT NULL UNIQUE, branch_name TEXT NOT NULL, base_commit TEXT NOT NULL, state TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS writer_leases (workspace_id TEXT PRIMARY KEY, owner TEXT NOT NULL, state TEXT NOT NULL, acquired_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS resource_inventory (resource_id TEXT PRIMARY KEY, resource_type TEXT NOT NULL, allocation_mode TEXT NOT NULL, capacity INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS resource_leases (id TEXT PRIMARY KEY, resource_id TEXT NOT NULL, task_key TEXT NOT NULL, owner TEXT NOT NULL, state TEXT NOT NULL, acquired_at TEXT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS active_exclusive_resource ON resource_leases(resource_id) WHERE state = 'active';
CREATE TABLE IF NOT EXISTS engineering_artifacts (id TEXT PRIMARY KEY, task_key TEXT NOT NULL, storage_reference TEXT NOT NULL, artifact_type TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS engineering_decisions (id TEXT PRIMARY KEY, task_key TEXT NOT NULL, decision TEXT NOT NULL, rationale TEXT NOT NULL, created_at TEXT NOT NULL);
