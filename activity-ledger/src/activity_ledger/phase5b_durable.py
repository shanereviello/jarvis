from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from .phase5b_evidence import CustodyResult, RetainedArtifact
from .worktree_allocator import HandoffDescriptor


SCHEMA = """
CREATE TABLE IF NOT EXISTS phase5b_claims (
    request_id TEXT PRIMARY KEY, claim_id TEXT NOT NULL UNIQUE, run_id TEXT,
    contract_sha256 TEXT NOT NULL, controller_id TEXT NOT NULL,
    attempt_number INTEGER NOT NULL, state TEXT NOT NULL,
    lease_expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS phase5b_bindings (
    request_id TEXT PRIMARY KEY, allocation_json TEXT NOT NULL,
    work_order_json TEXT
);
CREATE TABLE IF NOT EXISTS phase5b_artifacts (
    request_id TEXT NOT NULL, run_id TEXT NOT NULL, attempt_number INTEGER NOT NULL,
    artifact_type TEXT NOT NULL, artifact_json TEXT NOT NULL,
    PRIMARY KEY (request_id, run_id, attempt_number, artifact_type)
);
CREATE TABLE IF NOT EXISTS phase5b_commands (
    request_id TEXT NOT NULL, command_key TEXT NOT NULL, request_sha256 TEXT NOT NULL,
    response_json TEXT NOT NULL, PRIMARY KEY (request_id, command_key)
);
CREATE TABLE IF NOT EXISTS phase5b_writer_leases (
    allocation_id TEXT PRIMARY KEY, writer_id TEXT NOT NULL, owner_id TEXT NOT NULL,
    generation INTEGER NOT NULL, fence_sha256 TEXT NOT NULL, expires_at TEXT NOT NULL, state TEXT NOT NULL
);
"""


def _now() -> datetime:
    return datetime.now(UTC)


def _stamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _artifact(value: dict[str, Any]) -> RetainedArtifact:
    return RetainedArtifact(**value)


def _handoff(value: dict[str, Any]) -> HandoffDescriptor:
    return HandoffDescriptor(**value)


class DurablePhase5BStore:
    """SQLite-backed disposable stand-in for the Phase 5A durable adapter state.

    The schema mirrors the durable identity boundaries; PostgreSQL migration and
    live adapter execution remain separately authorized. Every operation opens a
    new connection so a fresh adapter instance exercises restart readback.
    """

    def __init__(self, database_path: Path, *, initialize: bool = False) -> None:
        self.database_path = Path(database_path)
        if initialize:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(self.database_path)) as connection, connection:
                connection.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path)

    def claim(self, request_id: str, contract_sha256: str, controller_id: str, attempt_number: int) -> dict[str, Any]:
        with closing(self._connect()) as db, db:
            row = db.execute("SELECT claim_id, run_id, contract_sha256, controller_id, attempt_number, state, lease_expires_at FROM phase5b_claims WHERE request_id=?", (request_id,)).fetchone()
            if row:
                if row[2:5] != (contract_sha256, controller_id, attempt_number):
                    raise ValueError("claim_conflict")
                return self._claim_dict(request_id, row)
            claim_id = str(uuid4())
            db.execute("INSERT INTO phase5b_claims VALUES (?, ?, NULL, ?, ?, ?, 'allocated', ?)", (request_id, claim_id, contract_sha256, controller_id, attempt_number, _stamp(_now() + timedelta(seconds=30))))
            return self._claim_dict(request_id, (claim_id, None, contract_sha256, controller_id, attempt_number, "allocated", db.execute("SELECT lease_expires_at FROM phase5b_claims WHERE request_id=?", (request_id,)).fetchone()[0]))

    @staticmethod
    def _claim_dict(request_id: str, row: tuple[Any, ...]) -> dict[str, Any]:
        return {"request_id": request_id, "claim_id": row[0], "run_id": row[1], "contract_sha256": row[2], "controller_id": row[3], "attempt_number": row[4], "state": row[5], "lease_valid": _parse(row[6]) > _now(), "lease_expires_at": row[6]}

    def bind_allocation(self, request_id: str, allocation: Any) -> HandoffDescriptor:
        value = allocation.as_dict() if hasattr(allocation, "as_dict") else dict(allocation)
        with closing(self._connect()) as db, db:
            row = db.execute("SELECT allocation_json FROM phase5b_bindings WHERE request_id=?", (request_id,)).fetchone()
            encoded = json.dumps(value, sort_keys=True, separators=(",", ":"))
            if row and row[0] != encoded:
                raise ValueError("allocation_conflict")
            if not row:
                db.execute("INSERT INTO phase5b_bindings(request_id, allocation_json) VALUES (?, ?)", (request_id, encoded))
        return _handoff(value)

    def read_allocation(self, request_id: str) -> HandoffDescriptor | None:
        with closing(self._connect()) as db, db:
            row = db.execute("SELECT allocation_json FROM phase5b_bindings WHERE request_id=?", (request_id,)).fetchone()
        return None if row is None else _handoff(json.loads(row[0]))

    def read_claim(self, request_id: str) -> dict[str, Any] | None:
        with closing(self._connect()) as db, db:
            row = db.execute("SELECT claim_id, run_id, contract_sha256, controller_id, attempt_number, state, lease_expires_at FROM phase5b_claims WHERE request_id=?", (request_id,)).fetchone()
        return None if row is None else self._claim_dict(request_id, row)

    def running(self, claim: dict[str, Any]) -> dict[str, Any]:
        with closing(self._connect()) as db, db:
            row = db.execute("SELECT run_id, contract_sha256, controller_id, attempt_number, state, lease_expires_at FROM phase5b_claims WHERE request_id=?", (claim["request_id"],)).fetchone()
            if row is None or row[5] <= _stamp(_now()):
                raise ValueError("ownership_expired")
            run_id = row[0] or str(uuid4())
            db.execute("UPDATE phase5b_claims SET run_id=?, state='running' WHERE request_id=?", (run_id, claim["request_id"]))
            return {**claim, "run_id": run_id, "state": "running", "lease_valid": True}

    def verifying(self, claim: dict[str, Any]) -> dict[str, Any]:
        self._require_active(claim)
        with closing(self._connect()) as db, db:
            db.execute("UPDATE phase5b_claims SET state='verifying' WHERE request_id=?", (claim["request_id"],))
        return {**claim, "state": "verifying"}

    def store_work_order(self, request_id: str, order: dict[str, Any]) -> None:
        encoded = json.dumps(order, sort_keys=True, separators=(",", ":"))
        with closing(self._connect()) as db, db:
            row = db.execute("SELECT work_order_json FROM phase5b_bindings WHERE request_id=?", (request_id,)).fetchone()
            if row is None:
                raise ValueError("allocation_binding_missing")
            if row[0] is not None and row[0] != encoded:
                raise ValueError("work_order_conflict")
            db.execute("UPDATE phase5b_bindings SET work_order_json=? WHERE request_id=?", (encoded, request_id))

    def read_work_order(self, request_id: str) -> dict[str, Any] | None:
        with closing(self._connect()) as db, db:
            row = db.execute("SELECT work_order_json FROM phase5b_bindings WHERE request_id=?", (request_id,)).fetchone()
        return None if row is None or row[0] is None else json.loads(row[0])

    def register_artifacts(self, custody: CustodyResult, claim: dict[str, Any]) -> dict[str, Any]:
        if custody.patch is None:
            raise ValueError("artifact_incomplete")
        records = (custody.result, custody.patch)
        with closing(self._connect()) as db, db:
            for record in records:
                key = (claim["request_id"], claim["run_id"], claim["attempt_number"], record.artifact_type)
                encoded = json.dumps(asdict(record), sort_keys=True, separators=(",", ":"))
                row = db.execute("SELECT artifact_json FROM phase5b_artifacts WHERE request_id=? AND run_id=? AND attempt_number=? AND artifact_type=?", key).fetchone()
                if row and row[0] != encoded:
                    raise ValueError("artifact_conflict")
                if not row:
                    db.execute("INSERT INTO phase5b_artifacts VALUES (?, ?, ?, ?, ?)", (*key, encoded))
        return {"duplicate": all(record.duplicate for record in records), "result": custody.result, "patch": custody.patch}

    def read_artifacts(self, claim: dict[str, Any]) -> CustodyResult | None:
        with closing(self._connect()) as db, db:
            rows = db.execute("SELECT artifact_type, artifact_json FROM phase5b_artifacts WHERE request_id=? AND run_id=? AND attempt_number=?", (claim["request_id"], claim["run_id"], claim["attempt_number"])).fetchall()
        records = {row[0]: _artifact(json.loads(row[1])) for row in rows}
        if "phase5b_codex_executor_result" not in records or "phase5b_codex_patch" not in records:
            return None
        return CustodyResult(records["phase5b_codex_executor_result"], records["phase5b_codex_patch"], True)

    def register_failure_artifact(self, artifact: RetainedArtifact, claim: dict[str, Any]) -> dict[str, Any]:
        """Disposable SQLite parity with the existing production failure interface."""
        self._require_active(claim)
        if artifact.artifact_type != 'phase5b_codex_failure':
            raise ValueError('artifact_conflict')
        key = (claim['request_id'], claim['run_id'], claim['attempt_number'], artifact.artifact_type)
        encoded = json.dumps(asdict(artifact), sort_keys=True, separators=(',', ':'))
        with closing(self._connect()) as db, db:
            row = db.execute('SELECT artifact_json FROM phase5b_artifacts WHERE request_id=? AND run_id=? AND attempt_number=? AND artifact_type=?', key).fetchone()
            if row and row[0] != encoded:
                raise ValueError('artifact_conflict')
            if not row:
                db.execute('INSERT INTO phase5b_artifacts VALUES (?, ?, ?, ?, ?)', (*key, encoded))
        return {'duplicate': row is not None, 'artifact': artifact}

    def read_failure_artifact(self, claim: dict[str, Any]) -> RetainedArtifact | None:
        key = (claim['request_id'], claim['run_id'], claim['attempt_number'], 'phase5b_codex_failure')
        with closing(self._connect()) as db, db:
            row = db.execute('SELECT artifact_json FROM phase5b_artifacts WHERE request_id=? AND run_id=? AND attempt_number=? AND artifact_type=?', key).fetchone()
        return None if row is None else _artifact(json.loads(row[0]))

    def finish(self, claim: dict[str, Any]) -> dict[str, Any]:
        self._require_active(claim)
        if self.read_artifacts(claim) is None:
            raise ValueError("finish_gate_failed")
        with closing(self._connect()) as db, db:
            db.execute("UPDATE phase5b_claims SET state='awaiting_review' WHERE request_id=?", (claim["request_id"],))
        if getattr(self, "finish_response_lost", False):
            raise RuntimeError("finish_response_lost")
        return {**claim, "state": "awaiting_review"}

    def fail(self, claim: dict[str, Any], classification: str) -> dict[str, Any]:
        with closing(self._connect()) as db, db:
            db.execute("UPDATE phase5b_claims SET state='closed' WHERE request_id=?", (claim["request_id"],))
        return {**claim, "state": "closed", "failure_classification": classification}

    def _require_active(self, claim: dict[str, Any]) -> None:
        if not claim.get("lease_valid") or _parse(claim["lease_expires_at"]) <= _now():
            raise ValueError("ownership_expired")

    def state(self, request_id: str) -> str | None:
        with closing(self._connect()) as db, db:
            row = db.execute("SELECT state FROM phase5b_claims WHERE request_id=?", (request_id,)).fetchone()
        return None if row is None else row[0]


class DurableWriterOwnership:
    """Durable fencing protocol; expiry does not stop a process by itself."""

    def __init__(self, store: DurablePhase5BStore, *, require_runtime_enforcement: bool = False, enforcement_available: bool = False) -> None:
        self.store = store
        self.require_runtime_enforcement = require_runtime_enforcement
        self.enforcement_available = enforcement_available

    def acquire(self, allocation: Any, claim: dict[str, Any]) -> dict[str, Any]:
        if self.require_runtime_enforcement and not self.enforcement_available:
            raise RuntimeError("writer_enforcement_unavailable")
        allocation_id = allocation.as_dict()["allocation_id"] if hasattr(allocation, "as_dict") else allocation["allocation_id"]
        writer_id = str(uuid4())
        generation = 1
        fence = hashlib.sha256(f"{writer_id}:{allocation_id}:{claim['attempt_number']}".encode()).hexdigest()
        expires = _stamp(_now() + timedelta(seconds=30))
        with closing(self.store._connect()) as db, db:
            row = db.execute("SELECT writer_id, state, expires_at FROM phase5b_writer_leases WHERE allocation_id=?", (allocation_id,)).fetchone()
            if row and row[1] == "active" and row[2] > _stamp(_now()):
                raise RuntimeError("writer_conflict")
            prior = db.execute("SELECT generation FROM phase5b_writer_leases WHERE allocation_id=?", (allocation_id,)).fetchone()
            generation = (prior[0] + 1) if prior else 1
            db.execute("INSERT OR REPLACE INTO phase5b_writer_leases VALUES (?, ?, ?, ?, ?, ?, 'active')", (allocation_id, writer_id, claim["controller_id"], generation, fence, expires))
        return {"writer_id": writer_id, "allocation_id": allocation_id, "generation": generation, "fence_sha256": fence, "expires_at": expires}

    def valid(self, owner: dict[str, Any]) -> bool:
        with closing(self.store._connect()) as db, db:
            row = db.execute("SELECT writer_id, generation, fence_sha256, state, expires_at FROM phase5b_writer_leases WHERE allocation_id=?", (owner["allocation_id"],)).fetchone()
        return bool(row and row[0] == owner["writer_id"] and row[1] == owner["generation"] and row[2] == owner["fence_sha256"] and row[3] == "active" and row[4] > _stamp(_now()))

    def release(self, owner: dict[str, Any]) -> None:
        with closing(self.store._connect()) as db, db:
            db.execute("UPDATE phase5b_writer_leases SET state='released' WHERE allocation_id=? AND writer_id=? AND generation=? AND fence_sha256=?", (owner["allocation_id"], owner["writer_id"], owner["generation"], owner["fence_sha256"]))


DurablePhase5BAdapter = DurablePhase5BStore
