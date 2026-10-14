from __future__ import annotations

import json
import sys
import types
import unittest
from pathlib import Path

_psycopg = types.ModuleType("psycopg")
setattr(_psycopg, "connect", None)
sys.modules.setdefault("psycopg", _psycopg)

from activity_ledger import pg_adapter

ROOT = Path(__file__).parents[1]


class FakeCursor:
    def __init__(self, existing=None, task=True) -> None:
        self.existing = existing
        self.task = task
        self.calls: list[tuple[str, tuple | None]] = []
        self._row = None
        self.sequence = 0

    def execute(self, sql: str, params=None) -> None:
        self.calls.append((sql, params))
        if "WHERE idempotency_key=%s FOR UPDATE" in sql and "execution_requests" in sql:
            self._row = self.existing
        elif "SELECT id FROM activity.tasks" in sql:
            self._row = ("task-id",) if self.task else None
        elif "COALESCE(MAX(sequence_number)" in sql:
            self.sequence += 1
            self._row = (self.sequence,)
        else:
            self._row = None

    def fetchone(self):
        row, self._row = self._row, None
        return row


class FakeDB:
    def __init__(self, commit_error: Exception | None = None) -> None:
        self.events: list[str] = []
        self.commit_error = commit_error

    def commit(self) -> None:
        self.events.append("commit")
        if self.commit_error:
            raise self.commit_error

    def rollback(self) -> None:
        self.events.append("rollback")


class Phase4ATransactionBehaviorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = json.loads((ROOT / "contracts/examples/bounded-code-modification.json").read_text())

    def test_commit_precedes_success_response(self) -> None:
        db = FakeDB()
        sent: list[tuple[int, dict]] = []
        pg_adapter._commit_then_respond(db, 200, {"ok": True}, lambda status, body: sent.append((status, body)))
        self.assertEqual(db.events, ["commit"])
        self.assertEqual(sent, [(200, {"ok": True})])

    def test_commit_failure_rolls_back_before_no_response(self) -> None:
        db = FakeDB(RuntimeError("commit failed"))
        sent: list[tuple[int, dict]] = []
        with self.assertRaises(RuntimeError):
            pg_adapter._commit_then_respond(db, 200, {"ok": True}, lambda status, body: sent.append((status, body)))
        self.assertEqual(db.events, ["commit", "rollback"])
        self.assertEqual(sent, [])

    def test_approval_and_cancellation_success_responses_use_post_commit_path(self) -> None:
        for result in ({"state": "queued"}, {"state": "closed"}):
            db = FakeDB()
            sent: list[tuple[int, dict]] = []
            pg_adapter._commit_then_respond(db, 200, result, lambda status, body: sent.append((status, body)))
            self.assertEqual(db.events, ["commit"])
            self.assertEqual(sent, [(200, result)])

    def test_submission_locks_key_before_existing_lookup_and_creates_three_history_records(self) -> None:
        cursor = FakeCursor()
        handler = object.__new__(pg_adapter.Handler)
        status, body = pg_adapter.Handler._submit(handler, cursor, {"contract": self.contract})
        self.assertEqual(status, 200)
        self.assertFalse(body["duplicate"])
        self.assertIn("pg_advisory_xact_lock", cursor.calls[0][0])
        self.assertIn("execution_requests", cursor.calls[1][0])
        self.assertEqual(sum("INSERT INTO activity.execution_request_events" in sql for sql, _ in cursor.calls), 3)

    def test_submission_accepts_colon_derived_idempotency_key(self) -> None:
        contract = dict(self.contract)
        contract["idempotency_key"] = "phase4b-runtime-canary-20260919-002:submission"
        handler = object.__new__(pg_adapter.Handler)
        status, body = pg_adapter.Handler._submit(handler, FakeCursor(), {"contract": contract})
        self.assertEqual(status, 200)
        self.assertFalse(body["duplicate"])

    def test_identical_retry_is_duplicate_and_conflicting_retry_is_409(self) -> None:
        _, contract_hash = pg_adapter.normalized_contract_sha256(self.contract)
        existing = ("request-id", contract_hash, "awaiting_execution_approval")
        handler = object.__new__(pg_adapter.Handler)
        status, body = pg_adapter.Handler._submit(handler, FakeCursor(existing=existing), {"contract": self.contract})
        self.assertEqual((status, body["duplicate"]), (200, True))
        changed = dict(self.contract)
        changed["objective"] = "different normalized content"
        status, body = pg_adapter.Handler._submit(handler, FakeCursor(existing=existing), {"contract": changed})
        self.assertEqual(status, 409)
        self.assertIn("conflicts", body["error"])

    def test_phase4a_handlers_return_values_and_do_not_emit_responses(self) -> None:
        source = (ROOT / "src/activity_ledger/pg_adapter.py").read_text()
        for name, next_name in (("def _submit", "def _approve"), ("def _approve", "def _cancel"), ("def _cancel", "def log_message")):
            section = source.split(name, 1)[1].split(next_name, 1)[0]
            self.assertNotIn("self._json", section)
        self.assertIn("_commit_then_respond(db, status, result, self._json)", source)
        self.assertIn("db.rollback()", source)

    def test_parent_lock_precedes_ordinary_child_idempotency_lookups(self) -> None:
        source = (ROOT / "src/activity_ledger/pg_adapter.py").read_text()
        approval = source.split("def _approve", 1)[1].split("def _cancel", 1)[0]
        cancellation = source.split("def _cancel", 1)[1].split("def log_message", 1)[0]
        self.assertIn("WHERE id=%s FOR UPDATE", approval)
        self.assertIn("WHERE execution_request_id=%s AND idempotency_key=%s\"", approval)
        self.assertNotIn("execution_approvals WHERE execution_request_id=%s AND idempotency_key=%s FOR UPDATE", approval)
        self.assertIn("WHERE id=%s FOR UPDATE", cancellation)
        self.assertIn("execution_request_events WHERE execution_request_id=%s AND idempotency_key=%s\"", cancellation)
        self.assertNotIn("execution_request_events WHERE execution_request_id=%s AND idempotency_key=%s FOR UPDATE", cancellation)


if __name__ == "__main__":
    unittest.main()
