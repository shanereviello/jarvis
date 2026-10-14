from __future__ import annotations

import sqlite3
import uuid
from contextlib import closing
import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class Task:
    id: str
    task_key: str
    title: str
    description: str
    origin_type: str
    state: str


class ActivityLedger:
    def __init__(self, database_path: Path) -> None:
        self.database_path = Path(database_path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def migrate(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection, connection:
            for migration_file in sorted((Path(__file__).parents[2] / "migrations").glob("*.sql")):
                version = int(migration_file.name.split("_", 1)[0])
                if version == 1 or connection.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (version,)).fetchone() is None:
                    connection.executescript(migration_file.read_text())
                    connection.execute("INSERT OR IGNORE INTO schema_migrations(version) VALUES (?)", (version,))

    def create_task(self, *, task_key: str, title: str, description: str, origin_type: str) -> Task:
        now = datetime.now(UTC).isoformat()
        task = Task(str(uuid.uuid4()), task_key, title, description, origin_type, "draft")
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """INSERT INTO engineering_tasks
                   (id, task_key, title, description, origin_type, state, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (task.id, task.task_key, task.title, task.description, task.origin_type, task.state, now, now),
            )
        return task

    def get_task(self, task_key: str) -> Task:
        with closing(self._connect()) as connection, connection:
            row = connection.execute("SELECT * FROM engineering_tasks WHERE task_key = ?", (task_key,)).fetchone()
        if row is None:
            raise KeyError(task_key)
        return Task(row["id"], row["task_key"], row["title"], row["description"], row["origin_type"], row["state"])

    def update_task_state(self, task_key: str, state: str) -> None:
        with closing(self._connect()) as connection, connection:
            if connection.execute("UPDATE engineering_tasks SET state=?, updated_at=? WHERE task_key=?", (state, datetime.now(UTC).isoformat(), task_key)).rowcount != 1:
                raise KeyError(task_key)

    def start_run(self, task_key: str, *, actor: str, source_interface: str) -> str:
        self.get_task(task_key)
        run_id = str(uuid.uuid4())
        with closing(self._connect()) as connection, connection:
            connection.execute("INSERT INTO engineering_runs VALUES (?, ?, ?, ?, ?, ?)", (run_id, task_key, actor, source_interface, "running", datetime.now(UTC).isoformat()))
        return run_id

    def append_event(self, run_id: str, event_type: str, payload: dict) -> None:
        with closing(self._connect()) as connection, connection:
            sequence = connection.execute("SELECT COALESCE(MAX(sequence_number), 0) + 1 FROM engineering_events WHERE run_id=?", (run_id,)).fetchone()[0]
            connection.execute("INSERT INTO engineering_events(run_id, sequence_number, event_type, payload, created_at) VALUES (?, ?, ?, ?, ?)", (run_id, sequence, event_type, json.dumps(payload, sort_keys=True), datetime.now(UTC).isoformat()))

    def events(self, run_id: str) -> list[dict]:
        with closing(self._connect()) as connection, connection:
            return [dict(row) for row in connection.execute("SELECT sequence_number,event_type,payload,created_at FROM engineering_events WHERE run_id=? ORDER BY sequence_number", (run_id,))]

    def register_workspace(self, task_key: str, path: str, branch: str, base_commit: str) -> str:
        workspace_id = str(uuid.uuid4())
        with closing(self._connect()) as connection, connection:
            connection.execute("INSERT INTO git_workspaces VALUES (?, ?, ?, ?, ?, ?)", (workspace_id, task_key, path, branch, base_commit, "allocated"))
        return workspace_id

    def acquire_writer(self, workspace_id: str, owner: str) -> None:
        with closing(self._connect()) as connection, connection:
            existing = connection.execute("SELECT owner FROM writer_leases WHERE workspace_id=? AND state='active'", (workspace_id,)).fetchone()
            if existing: raise RuntimeError(f"writer lease held by {existing['owner']}")
            connection.execute("INSERT OR REPLACE INTO writer_leases VALUES (?, ?, 'active', ?)", (workspace_id, owner, datetime.now(UTC).isoformat()))

    def register_resource(self, resource_id: str, resource_type: str, allocation_mode: str, capacity: int) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute("INSERT INTO resource_inventory VALUES (?, ?, ?, ?)", (resource_id, resource_type, allocation_mode, capacity))

    def acquire_resources(self, task_key: str, resource_ids: list[str], owner: str) -> None:
        with closing(self._connect()) as connection, connection:
            for resource_id in resource_ids:
                row = connection.execute("SELECT allocation_mode FROM resource_inventory WHERE resource_id=?", (resource_id,)).fetchone()
                if row is None: raise KeyError(resource_id)
                if row['allocation_mode'] == 'exclusive' and connection.execute("SELECT 1 FROM resource_leases WHERE resource_id=? AND state='active'", (resource_id,)).fetchone(): raise RuntimeError(f"resource lease held: {resource_id}")
            for resource_id in resource_ids:
                connection.execute("INSERT INTO resource_leases VALUES (?, ?, ?, ?, 'active', ?)", (str(uuid.uuid4()), resource_id, task_key, owner, datetime.now(UTC).isoformat()))

    def project_kanban(self, task_key: str, card: dict) -> dict:
        task = self.get_task(task_key)
        if card.get('task_key') != task.task_key or card.get('state') != task.state:
            return {'status': 'drift', 'canonical_task_key': task.task_key, 'canonical_state': task.state, 'card': card}
        return {'status': 'in_sync', 'canonical_task_key': task.task_key}

    def allocate_worktree(self, task_key: str, source_repository: Path, task_root: Path) -> Path:
        task = self.get_task(task_key)
        target = Path(task_root) / task.task_key / "repo"
        if target.exists():
            raise RuntimeError(f"workspace already exists: {target}")
        target.parent.mkdir(parents=True, exist_ok=False)
        branch = f"codex/{task.task_key}"
        base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source_repository, text=True).strip()
        try:
            subprocess.run(["git", "worktree", "add", "-b", branch, str(target), base], cwd=source_repository, check=True, capture_output=True, text=True)
            self.register_workspace(task_key, str(target), branch, base)
        except Exception:
            if target.exists(): subprocess.run(["git", "worktree", "remove", "--force", str(target)], cwd=source_repository, check=False, capture_output=True)
            raise
        return target
