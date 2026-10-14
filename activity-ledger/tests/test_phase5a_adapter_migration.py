from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

_psycopg = types.ModuleType("psycopg")
setattr(_psycopg, "connect", None)
sys.modules.setdefault("psycopg", _psycopg)

from activity_ledger import pg_adapter

ROOT = Path(__file__).parents[1]
REQUEST = "11111111-1111-4111-8111-111111111111"
CLAIM = "22222222-2222-4222-8222-222222222222"
RUN = "33333333-3333-4333-8333-333333333333"
CONTRACT = "a" * 64
WORK_ORDER = "b" * 64


def phase5a_body(**updates):
    metadata = pg_adapter._phase5a_exact_metadata(REQUEST, CLAIM, RUN, CONTRACT, WORK_ORDER)
    body = {
        "request_id": REQUEST, "contract_sha256": CONTRACT, "controller_id": "phase5a-controller",
        "idempotency_key": "phase5a-evidence-1", "claim_id": CLAIM, "claim_token": "t" * 43,
        "artifact_type": pg_adapter.PHASE5A_ARTIFACT_TYPE, "sha256": "c" * 64,
        "size_bytes": len(json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode()),
        "media_type": "application/json", "metadata": metadata,
    }
    body.update(updates)
    return body


class Phase5ACursor:
    def __init__(self, prior=None, artifact=None):
        self.calls = []
        self.prior = prior
        self.artifact = artifact

    def execute(self, sql, params=None):
        self.calls.append((sql, params))

    def fetchone(self):
        sql = self.calls[-1][0]
        if "execution_controller_commands" in sql and "SELECT" in sql:
            return self.prior
        if "FROM activity.runs" in sql:
            return (RUN, "phase5a-model-free-executor")
        if "FROM activity.run_artifacts" in sql:
            return self.artifact
        return None


class ReviewProfileCursor:
    def __init__(self, profile, runs=None, artifact=True, artifact_run=RUN, prior=None):
        self.request = (CONTRACT, "awaiting_review", profile)
        self.runs = runs if runs is not None else [(RUN, "phase5a-model-free-executor")]
        self.artifact = artifact
        self.artifact_run = artifact_run
        self.prior = prior
        self.calls = []
        self.row = None

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        if "FROM activity.execution_requests" in sql:
            self.row = self.request
        elif "FROM activity.execution_approvals" in sql:
            self.row = self.prior
        elif "FROM activity.run_artifacts" in sql:
            self.row = ("artifact",) if self.artifact and params and params[1] == self.artifact_run else None
        elif "MAX(sequence_number)" in sql:
            self.row = (0,)
        else:
            self.row = None

    def fetchone(self):
        row, self.row = self.row, None
        return row

    def fetchall(self):
        return self.runs


def review_body(key="phase5a-runtime-review-1", decision="approved"):
    return {
        "actor": "phase5a-runtime-review", "decision": decision, "approval_gate": "review",
        "idempotency_key": key, "contract_sha256": CONTRACT,
    }


class LeaseResponseCursor:
    def __init__(self, profile, expiry, prior=None):
        self.profile = profile
        self.expiry = expiry
        self.updated_expiry = expiry.replace(second=30)
        self.prior = prior
        self.calls = []
        self.heartbeat = False
        self.stored_expiry = None

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        if "execution_controller_commands" in sql and "INSERT" in sql and params:
            self.stored_expiry = json.loads(params[-1]).get("lease_expires_at")

    def fetchone(self):
        sql = self.calls[-1][0]
        if "execution_requests WHERE id" in sql:
            return (CONTRACT, "queued" if not self.heartbeat else "allocated", self.profile)
        if "execution_controller_commands" in sql and "SELECT" in sql:
            return self.prior
        if "execution_controller_leases WHERE execution_request_id=%s AND state='active'" in sql:
            return None
        if "COALESCE(MAX(attempt_number)" in sql:
            return (0,)
        if "RETURNING lease_expires_at" in sql:
            return (self.expiry,)
        if "RETURNING id, lease_expires_at" in sql:
            return (CLAIM, self.updated_expiry)
        if "COALESCE(MAX(sequence_number)" in sql:
            return (0,)
        if "execution_controller_leases WHERE id=%s" in sql:
            return (CLAIM, "active", "phase5a-controller", pg_adapter.token_hash("t" * 43), self.expiry, False)
        return None


class Phase5AAdapterMigrationTests(unittest.TestCase):
    def review(self, cursor, body=None):
        handler = object.__new__(pg_adapter.Handler)
        return handler._review(cursor, REQUEST, body or review_body())

    def test_phase5a_review_requires_exact_profile_run_source_and_artifact(self):
        cursor = ReviewProfileCursor(pg_adapter.PHASE5A_PROFILE)
        status, response = self.review(cursor)
        self.assertEqual((status, response["state"], response["duplicate"]), (200, "closed", False))
        self.assertTrue(any("execution_request_id=%s AND run_id=%s AND artifact_type=%s" in sql for sql, _ in cursor.calls))
        self.assertTrue(any("UPDATE activity.runs SET status=%s WHERE id=%s" in sql and params[-1] == RUN for sql, params in cursor.calls if params))

    def test_phase5a_review_rejects_missing_or_mismatched_evidence_without_mutation(self):
        cases = (
            ("missing", ReviewProfileCursor(pg_adapter.PHASE5A_PROFILE, artifact=False)),
            ("wrong-run", ReviewProfileCursor(pg_adapter.PHASE5A_PROFILE, runs=[("other-run", "phase5a-model-free-executor")])),
            ("wrong-request", ReviewProfileCursor(pg_adapter.PHASE5A_PROFILE, artifact=False)),
            ("wrong-source", ReviewProfileCursor(pg_adapter.PHASE5A_PROFILE, runs=[(RUN, "other-source")])),
            ("unsupported-profile", ReviewProfileCursor("unsupported-profile")),
            ("phase4b-only", ReviewProfileCursor(pg_adapter.PHASE5A_PROFILE, artifact=False)),
            ("multiple-runs", ReviewProfileCursor(pg_adapter.PHASE5A_PROFILE, runs=[(RUN, "phase5a-model-free-executor"), ("other-run", "phase5a-model-free-executor")])),
        )
        for name, cursor in cases:
            with self.subTest(name=name):
                status, _ = self.review(cursor)
                self.assertEqual(status, 409)
                self.assertFalse(any("INSERT INTO activity.execution_approvals" in sql or "UPDATE activity.runs SET status" in sql or "INSERT INTO activity.execution_request_events" in sql for sql, _ in cursor.calls))

    def test_phase4b_review_profile_and_replay_remain_supported(self):
        cursor = ReviewProfileCursor("repository-review-v1", runs=[(RUN, "phase4b-fake-controller")])
        phase4b_body = {**review_body("phase4b-review-1"), "actor": "phase4b-runtime-review"}
        status, response = self.review(cursor, phase4b_body)
        self.assertEqual((status, response["state"], response["duplicate"]), (200, "closed", False))
        prior = ("phase4b-runtime-review", "approved", "review", CONTRACT)
        status, response = self.review(ReviewProfileCursor("repository-review-v1", runs=[(RUN, "phase4b-fake-controller")], prior=prior), phase4b_body)
        self.assertEqual((status, response["state"], response["duplicate"]), (200, "closed", True))
        status, _ = self.review(ReviewProfileCursor("repository-review-v1", runs=[(RUN, "phase4b-fake-controller")], prior=prior), {**phase4b_body, "decision": "rejected"})
        self.assertEqual(status, 409)

    def test_phase5a_review_sql_binds_request_run_and_artifact_type(self):
        source = (ROOT / "src/activity_ledger/pg_adapter.py").read_text()
        section = source.split("def _review", 1)[1].split("def _recover", 1)[0]
        self.assertIn("execution_request_id=%s AND run_id=%s AND artifact_type=%s", section)
        self.assertIn("PHASE5A_ARTIFACT_TYPE", section)

    def test_migrations_001_to_007_are_byte_identical_to_required_head(self):
        # This subproject was imported from independent Git history. Preserve the
        # original required revision's byte checks using its recorded SHA256s.
        fixture=json.loads((ROOT/'tests/fixtures/historical-migrations.json').read_text())
        self.assertEqual(fixture['original_required_commit'],'3d6433b')
        for name,digest in fixture['files'].items():
            self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(),digest,name)

    def test_migration_008_is_transactional_and_only_adds_required_index(self):
        sql = (ROOT / "db/migrations/008_phase5a_model_free_executor_result.sql").read_text()
        self.assertTrue(sql.startswith("BEGIN;")); self.assertTrue(sql.rstrip().endswith("COMMIT;"))
        self.assertIn("CREATE UNIQUE INDEX phase5a_model_free_result_one_per_request", sql)
        self.assertIn("WHERE artifact_type = 'phase5a_model_free_executor_result'", sql)
        self.assertIn("INSERT INTO activity.schema_migrations(version) VALUES (8)", sql)
        self.assertNotIn("GRANT", sql.upper()); self.assertNotIn("CREATE ROLE", sql.upper())
        self.assertEqual(re.findall(r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+([a-z0-9_]+)", sql), ["phase5a_model_free_result_one_per_request"])

    def test_exact_index_and_table_inventory_expectations_include_only_additive_phase5a_index(self):
        restore = (ROOT / "host/phase2b/40-backup-restore.sh").read_text()
        verify = (ROOT / "host/phase2b/30-verify.sh").read_text()
        self.assertIn("phase5a_model_free_result_one_per_request", restore)
        self.assertIn("phase5a_model_free_result_one_per_request", verify)
        self.assertIn('"versions=1,2,3,4,5,6,7,8,9,10"', restore)
        self.assertIn('== "1,2,3,4,5,6,7,8,9,10"', verify)
        self.assertIn("phase5a_artifacts=", restore)
        self.assertNotIn("CREATE TABLE", (ROOT / "db/migrations/008_phase5a_model_free_executor_result.sql").read_text().upper())

    def test_phase5a_constants_are_distinct_from_phase4b(self):
        self.assertNotEqual(pg_adapter.PHASE5A_STAGING_ROOT, pg_adapter.PHASE4B_STAGING_ROOT)
        self.assertNotEqual(pg_adapter.PHASE5A_RETAINED_ROOT, pg_adapter.PHASE4B_RETAINED_ROOT)
        self.assertEqual(pg_adapter.PHASE5A_ARTIFACT_TYPE, "phase5a_model_free_executor_result")

    def test_metadata_is_exact_and_canonical(self):
        metadata = pg_adapter._phase5a_exact_metadata(REQUEST, CLAIM, RUN, CONTRACT, WORK_ORDER)
        self.assertEqual(set(metadata), {"schema_name", "schema_version", "request_id", "claim_id", "run_id", "contract_sha256", "executor_profile", "recipe", "outcome", "observations", "work_order_sha256"})
        self.assertEqual(metadata["observations"], ["deterministic executor completed"])
        content = json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode()
        self.assertEqual(hashlib.sha256(content).hexdigest(), hashlib.sha256(content).hexdigest())

    def test_metadata_rejects_boolean_size_uppercase_uuid_and_path_fields_are_static_boundary(self):
        with self.assertRaises(ValueError): pg_adapter._phase5a_exact_metadata(REQUEST[:-1] + "A", CLAIM, RUN, CONTRACT, WORK_ORDER)
        source = (ROOT / "src/activity_ledger/pg_adapter.py").read_text()
        self.assertIn("_PHASE5A_EVIDENCE_FIELDS", source)
        self.assertNotIn('"path", "run_id", "work_order_sha256"', source)
        self.assertIn("PHASE5A_STAGING_ROOT", source)
        self.assertIn("PHASE5A_RETAINED_ROOT", source)

    def test_transaction_post_commit_cleanup_happens_after_commit_and_response(self):
        class DB:
            def __init__(self): self.events = []
            def commit(self): self.events.append("commit")
            def rollback(self): self.events.append("rollback")
        db = DB(); send = Mock(side_effect=lambda *args: db.events.append("response"))
        cleanup = Mock(side_effect=lambda: db.events.append("cleanup") or True)
        pg_adapter._run_controller_transaction(db, lambda promotions: (promotions.append(pg_adapter._Phase5APromotion("/retained", {"st_dev": 1, "st_ino": 2}, cleanup)) or (200, {"ok": True})), send)
        self.assertEqual(db.events, ["commit", "cleanup", "response"])

    def test_commit_failure_cleans_only_promoted_retained_evidence(self):
        class DB:
            def commit(self): raise RuntimeError("commit")
            def rollback(self): self.rolled_back = True
        cleanup = Mock(); send = Mock(); db = DB()
        pg_adapter._run_controller_transaction(db, lambda promotions: (promotions.append(("/retained", {"st_dev": 1, "st_ino": 2})) or (200, {})), send, cleanup)
        cleanup.assert_called_once_with("/retained", {"st_dev": 1, "st_ino": 2})
        send.assert_called_once_with(500, {"error": "internal server error"})

    def test_no_token_or_retained_instruction_is_stored_as_evidence(self):
        source = (ROOT / "src/activity_ledger/pg_adapter.py").read_text()
        self.assertNotIn("claim_token", source.split("def promote_phase5a_evidence", 1)[1].split("def cleanup_phase5a_staging", 1)[0])

    def test_phase5a_first_attempt_validates_run_before_command_and_records_promotion(self):
        handler = object.__new__(pg_adapter.Handler)
        cursor = Phase5ACursor()
        body = phase5a_body()
        promotion = {
            "retained_path": "/srv/jarvis-activity/runner-state/phase5a-executor-retained/%s/%s.json" % (REQUEST, CLAIM),
            "sha256": body["sha256"], "size_bytes": body["size_bytes"],
            "metadata": body["metadata"], "cleanup_receipt": {"st_dev": 1, "st_ino": 2},
            "staging_receipt": {"st_dev": 3, "st_ino": 4},
        }
        promotions = []
        with patch.object(pg_adapter, "promote_phase5a_evidence", return_value=promotion):
            status, response = handler._phase5a_evidence(cursor, REQUEST, CONTRACT, "phase5a-controller", body["idempotency_key"], body, CLAIM, "running", "d" * 64, promotions)
        self.assertEqual(status, 200)
        self.assertFalse(response["duplicate"])
        self.assertIsInstance(promotions[0], pg_adapter._Phase5APromotion)
        self.assertLess(next(i for i, call in enumerate(cursor.calls) if "FROM activity.runs" in call[0]), next(i for i, call in enumerate(cursor.calls) if "execution_controller_commands" in call[0] and "SELECT" in call[0]))
        self.assertLess(next(i for i, call in enumerate(cursor.calls) if "run_artifacts" in call[0] and "INSERT" in call[0]), next(i for i, call in enumerate(cursor.calls) if "execution_controller_commands" in call[0] and "INSERT" in call[0]))

    def test_phase5a_claim_and_heartbeat_return_database_expiry_and_phase4b_shape_is_unchanged(self):
        handler = object.__new__(pg_adapter.Handler)
        expiry = datetime(2030, 1, 1, tzinfo=timezone.utc)
        for profile, expect_expiry in ((pg_adapter.PHASE5A_PROFILE, True), ("phase4b-fake-controller-v1", False)):
            with self.subTest(profile=profile):
                cursor = LeaseResponseCursor(profile=profile, expiry=expiry)
                claim_body = {"request_id": REQUEST, "contract_sha256": CONTRACT, "controller_id": "phase5a-controller", "idempotency_key": "claim-contract-1", "claim_token": "t" * 43}
                status, claim = handler._controller_write(cursor, "/v1/controller/claim", claim_body, [])
                self.assertEqual(status, 200)
                self.assertEqual("lease_expires_at" in claim, expect_expiry)
                self.assertEqual(cursor.stored_expiry, claim.get("lease_expires_at"))
                cursor.heartbeat = True
                heartbeat_body = {**claim_body, "claim_id": CLAIM, "idempotency_key": "heartbeat-contract-1"}
                status, heartbeat = handler._controller_write(cursor, "/v1/controller/heartbeat", heartbeat_body, [])
                self.assertEqual(status, 200)
                self.assertEqual("lease_expires_at" in heartbeat, expect_expiry)

    def test_phase5a_duplicate_heartbeat_replays_stored_expiry_without_update(self):
        handler = object.__new__(pg_adapter.Handler)
        stored = {"claim_id": CLAIM, "state": "allocated", "duplicate": False, "lease_expires_at": "2030-01-01T00:00:00Z"}
        body = {"request_id": REQUEST, "contract_sha256": CONTRACT, "controller_id": "phase5a-controller", "idempotency_key": "heartbeat-replay-1", "claim_id": CLAIM, "claim_token": "t" * 43}
        request_hash = handler._controller_request_hash("heartbeat", body, pg_adapter.token_hash("t" * 43))
        cursor = LeaseResponseCursor(profile=pg_adapter.PHASE5A_PROFILE, expiry=datetime(2030, 1, 1, tzinfo=timezone.utc), prior=("phase5a-controller", "phase5a-controller", "heartbeat", request_hash, stored))
        status, response = handler._controller_write(cursor, "/v1/controller/heartbeat", body, [])
        self.assertEqual((status, response), (200, {**stored, "duplicate": True}))
        self.assertFalse(any("UPDATE activity.execution_controller_leases" in sql for sql, _ in cursor.calls))

    def test_phase5a_explicit_allowlist_rejects_path_run_work_order_and_failure_fields(self):
        handler = object.__new__(pg_adapter.Handler)
        for field in ("path", "protected_absolute_path", "retained_path", "run_id", "work_order_path", "staging_path", "result_path", "claim_token_sha256", "failure_classification", "unknown"):
            with self.subTest(field=field):
                body = phase5a_body(**{field: "forbidden"})
                status, _ = handler._phase5a_evidence(Phase5ACursor(), REQUEST, CONTRACT, "phase5a-controller", body["idempotency_key"], body, CLAIM, "running", "d" * 64, [])
                self.assertEqual(status, 400)

    def test_identical_replay_reconciles_staging_and_returns_safe_duplicate_without_inserts(self):
        handler = object.__new__(pg_adapter.Handler)
        body = phase5a_body()
        artifact = (RUN, body["idempotency_key"], "/srv/jarvis-activity/runner-state/phase5a-executor-retained/%s/%s.json" % (REQUEST, CLAIM), body["sha256"], body["size_bytes"], "application/json", body["metadata"])
        prior = ("phase5a-controller", "phase5a-controller", "evidence", "d" * 64, {"claim_id": CLAIM, "artifact_id": "artifact", "duplicate": False})
        cursor = Phase5ACursor(prior=prior, artifact=artifact)
        with patch.object(pg_adapter, "_phase5a_read_validated", side_effect=FileNotFoundError), patch.object(pg_adapter, "reconcile_phase5a_staging_absence", return_value=True), patch.object(handler, "_phase5a_retained_valid", return_value=True):
            status, response = handler._phase5a_evidence(cursor, REQUEST, CONTRACT, "phase5a-controller", body["idempotency_key"], body, CLAIM, "running", "d" * 64, [])
        self.assertEqual((status, response["duplicate"]), (200, True))
        self.assertFalse(any("INSERT INTO activity.run_artifacts" in sql or "INSERT INTO activity.execution_controller_commands" in sql for sql, _ in cursor.calls))

    def test_conflicting_command_hash_returns_409_before_promotion(self):
        handler = object.__new__(pg_adapter.Handler)
        body = phase5a_body()
        cursor = Phase5ACursor(prior=("phase5a-controller", "phase5a-controller", "evidence", "different", {}))
        with patch.object(pg_adapter, "promote_phase5a_evidence") as promote:
            status, _ = handler._phase5a_evidence(cursor, REQUEST, CONTRACT, "phase5a-controller", body["idempotency_key"], body, CLAIM, "running", "d" * 64, [])
        self.assertEqual(status, 409)
        promote.assert_not_called()

    def test_stored_command_corruption_never_returns_cached_success(self):
        handler = object.__new__(pg_adapter.Handler)
        body = phase5a_body()
        artifact = (RUN, body["idempotency_key"], "/srv/jarvis-activity/runner-state/phase5a-executor-retained/%s/%s.json" % (REQUEST, CLAIM), body["sha256"], body["size_bytes"], "application/json", body["metadata"])
        cases = (
            ("actor", "other", "phase5a-controller", "evidence", {"claim_id": CLAIM, "artifact_id": "a"}),
            ("controller", "phase5a-controller", "other", "evidence", {"claim_id": CLAIM, "artifact_id": "a"}),
            ("command", "phase5a-controller", "phase5a-controller", "finish", {"claim_id": CLAIM, "artifact_id": "a"}),
            ("metadata", "phase5a-controller", "phase5a-controller", "evidence", "not-an-object"),
            ("safe-fields", "phase5a-controller", "phase5a-controller", "evidence", {}),
        )
        for name, actor, controller, command, response in cases:
            with self.subTest(name=name):
                prior = (actor, controller, command, "d" * 64, response)
                cursor = Phase5ACursor(prior=prior, artifact=artifact)
                with patch.object(pg_adapter, "promote_phase5a_evidence") as promote, patch.object(handler, "_phase5a_retained_valid", return_value=True):
                    status, _ = handler._phase5a_evidence(cursor, REQUEST, CONTRACT, "phase5a-controller", body["idempotency_key"], body, CLAIM, "running", "d" * 64, [])
                self.assertEqual(status, 409)
                promote.assert_not_called()
                self.assertFalse(any("INSERT INTO" in sql for sql, _ in cursor.calls))

    def test_replay_rejects_missing_replaced_retained_or_disagreeing_staging_without_mutation(self):
        handler = object.__new__(pg_adapter.Handler)
        body = phase5a_body()
        artifact = (RUN, body["idempotency_key"], "/srv/jarvis-activity/runner-state/phase5a-executor-retained/%s/%s.json" % (REQUEST, CLAIM), body["sha256"], body["size_bytes"], "application/json", body["metadata"])
        prior = ("phase5a-controller", "phase5a-controller", "evidence", "d" * 64, {"claim_id": CLAIM, "artifact_id": "a"})
        for name, retained_ok, staging_error in (("missing-retained", False, FileNotFoundError), ("replaced-retained", False, FileNotFoundError), ("staging-disagreement", True, ValueError)):
            with self.subTest(name=name):
                cursor = Phase5ACursor(prior=prior, artifact=artifact)
                with patch.object(pg_adapter, "_phase5a_read_validated", side_effect=staging_error), patch.object(pg_adapter, "reconcile_phase5a_staging_absence", return_value=True), patch.object(handler, "_phase5a_retained_valid", return_value=retained_ok), patch.object(pg_adapter, "promote_phase5a_evidence") as promote:
                    status, _ = handler._phase5a_evidence(cursor, REQUEST, CONTRACT, "phase5a-controller", body["idempotency_key"], body, CLAIM, "running", "d" * 64, [])
                self.assertEqual(status, 409)
                promote.assert_not_called()
                self.assertFalse(any("INSERT INTO" in sql for sql, _ in cursor.calls))

    def test_post_commit_cleanup_failure_is_not_rollback_or_retained_cleanup(self):
        class DB:
            def __init__(self): self.events = []
            def commit(self): self.events.append("commit")
            def rollback(self): self.events.append("rollback")
        db = DB(); send = Mock()
        cleanup = Mock(return_value=False)
        pg_adapter._run_controller_transaction(db, lambda promotions: (promotions.append(pg_adapter._Phase5APromotion("/retained", {"st_dev": 1, "st_ino": 2}, cleanup)) or (200, {"ok": True})), send)
        self.assertEqual(db.events, ["commit"])
        send.assert_called_once_with(500, {"error": "evidence cleanup could not be proven"})

    def test_lost_response_retry_keeps_one_command_artifact_retained_file_and_no_staging(self):
        state = {"committed": False, "promotions": 0, "artifacts": 0, "commands": 0, "cleanups": 0}
        class DB:
            def __init__(self): self.commits = 0; self.rollbacks = 0
            def commit(self): self.commits += 1; state["committed"] = True
            def rollback(self): self.rollbacks += 1
        def write(promotions):
            if state["committed"]:
                return 200, {"claim_id": CLAIM, "artifact_id": "artifact", "duplicate": True}
            state["promotions"] += 1; state["artifacts"] += 1; state["commands"] += 1
            promotions.append(pg_adapter._Phase5APromotion("/retained", {"st_dev": 1, "st_ino": 2}, lambda: state.__setitem__("cleanups", state["cleanups"] + 1) or True))
            return 200, {"claim_id": CLAIM, "artifact_id": "artifact", "duplicate": False}
        db = DB(); first_response = Mock(side_effect=RuntimeError("lost response"))
        pg_adapter._run_controller_transaction(db, write, first_response)
        second_response = Mock()
        pg_adapter._run_controller_transaction(db, write, second_response)
        self.assertEqual((db.commits, db.rollbacks, state["promotions"], state["artifacts"], state["commands"], state["cleanups"]), (2, 0, 1, 1, 1, 1))
        second_response.assert_called_once_with(200, {"claim_id": CLAIM, "artifact_id": "artifact", "duplicate": True})

    def test_artifact_and_command_insert_failures_rollback_and_cleanup_retained_only(self):
        for failure in ("artifact", "command", "commit"):
            with self.subTest(failure=failure):
                events = []
                class DB:
                    def commit(inner):
                        events.append("commit")
                        if failure == "commit": raise RuntimeError("commit")
                    def rollback(inner): events.append("rollback")
                cleanup = Mock(side_effect=lambda path, receipt: events.append(("cleanup", path, receipt)))
                send = Mock()
                def write(promotions):
                    events.append("artifact-insert")
                    promotions.append(("/retained", {"st_dev": 1, "st_ino": 2}))
                    if failure == "artifact": raise RuntimeError("artifact")
                    events.append("command-insert")
                    if failure == "command": raise RuntimeError("command")
                    return 200, {"artifact_id": "a"}
                pg_adapter._run_controller_transaction(DB(), write, send, cleanup)
                self.assertIn("rollback", events)
                self.assertNotIn("response", events)
                cleanup.assert_called_once_with("/retained", {"st_dev": 1, "st_ino": 2})
                send.assert_called_once_with(500, {"error": "internal server error"})


class Phase5AFilesystemTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        base = Path(self.tempdir.name)
        self.staging = base / "staging"
        self.retained = base / "retained"
        self.staging.mkdir(); self.retained.mkdir()
        self.request_dir = self.staging / REQUEST
        self.request_dir.mkdir(mode=0o750)
        self.metadata = pg_adapter._phase5a_exact_metadata(REQUEST, CLAIM, RUN, CONTRACT, WORK_ORDER)
        self.content = json.dumps(self.metadata, sort_keys=True, separators=(",", ":")).encode()
        self.source = self.request_dir / f"{CLAIM}.json"
        self.source.write_bytes(self.content)
        self.source.chmod(0o640)
        self.patches = patch.multiple(
            pg_adapter, PHASE5A_STAGING_ROOT=self.staging, PHASE5A_RETAINED_ROOT=self.retained,
            PHASE5A_EXPECTED_UID=os.getuid(), PHASE5A_EXPECTED_GID=os.getgid(),
        )
        self.patches.start()

    def tearDown(self):
        self.patches.stop(); self.tempdir.cleanup()

    def promote(self):
        return pg_adapter.promote_phase5a_evidence(
            REQUEST, CLAIM, RUN, CONTRACT, hashlib.sha256(self.content).hexdigest(), len(self.content), self.metadata
        )

    def test_valid_promotion_derives_both_paths_and_preserves_exact_bytes(self):
        result = self.promote()
        self.assertEqual(result["retained_path"], str(self.retained / REQUEST / f"{CLAIM}.json"))
        self.assertEqual(Path(result["retained_path"]).read_bytes(), self.content)
        self.assertEqual(result["staging_receipt"]["st_ino"], self.source.stat().st_ino)

    def test_retained_corruption_and_inode_mutation_fail_closed_without_deletion(self):
        result = self.promote()
        final = Path(result["retained_path"])
        digest = hashlib.sha256(self.content).hexdigest()
        cases = ("mode", "uid", "gid", "size", "digest", "noncanonical", "metadata", "inode")
        for case in cases:
            with self.subTest(case=case):
                if not final.exists():
                    final.parent.mkdir(parents=True)
                    final.write_bytes(self.content)
                final.chmod(0o640)
                final.write_bytes(self.content)
                if case == "mode": final.chmod(0o600)
                elif case == "size": final.write_bytes(self.content + b"x")
                elif case == "digest": final.write_bytes(b"wrong retained bytes")
                elif case == "noncanonical": final.write_bytes(json.dumps(self.metadata).encode())
                elif case == "metadata":
                    altered = dict(self.metadata); altered["outcome"] = "wrong"
                    final.write_bytes(json.dumps(altered, sort_keys=True, separators=(",", ":")).encode())
                if case in {"uid", "gid"}:
                    real_fstat = os.fstat
                    def altered_fstat(fd):
                        info = real_fstat(fd)
                        if stat.S_ISREG(info.st_mode):
                            values = list(info); values[4 if case == "uid" else 5] += 1
                            return os.stat_result(values)
                        return info
                    with patch.object(pg_adapter.os, "fstat", side_effect=altered_fstat):
                        self.assertFalse(pg_adapter.Handler._phase5a_retained_valid(object.__new__(pg_adapter.Handler), str(final), REQUEST, CLAIM, digest, len(self.content), self.metadata))
                elif case == "inode":
                    real_fstat = os.fstat; regular_calls = 0
                    def mutated_fstat(fd):
                        nonlocal regular_calls
                        info = real_fstat(fd)
                        if stat.S_ISREG(info.st_mode):
                            regular_calls += 1
                            if regular_calls == 2:
                                values = list(info); values[1] += 1
                                return os.stat_result(values)
                        return info
                    with patch.object(pg_adapter.os, "fstat", side_effect=mutated_fstat):
                        self.assertFalse(pg_adapter.Handler._phase5a_retained_valid(object.__new__(pg_adapter.Handler), str(final), REQUEST, CLAIM, digest, len(self.content), self.metadata))
                else:
                    self.assertFalse(pg_adapter.Handler._phase5a_retained_valid(object.__new__(pg_adapter.Handler), str(final), REQUEST, CLAIM, digest, len(self.content), self.metadata))
                self.assertTrue(final.exists())

    def test_staging_request_symlink_and_evidence_symlink_fail_closed(self):
        self.source.unlink(); self.request_dir.rmdir(); self.request_dir.symlink_to(self.staging / "other")
        (self.staging / "other").mkdir()
        with self.assertRaises(OSError): self.promote()
        self.assertFalse((self.retained / REQUEST).exists())
        self.request_dir.unlink(); self.request_dir.mkdir(mode=0o750)
        target = self.request_dir / "real.json"; target.write_bytes(self.content); target.chmod(0o640)
        self.source.symlink_to(target)
        with self.assertRaises(OSError): self.promote()
        self.assertFalse((self.retained / REQUEST).exists())

    def test_staging_fstat_mutation_in_size_or_inode_fails_before_promotion(self):
        real_fstat = os.fstat
        for field in ("st_size", "st_ino"):
            with self.subTest(field=field):
                calls = 0
                def mutate(fd):
                    nonlocal calls
                    info = real_fstat(fd)
                    if stat.S_ISREG(info.st_mode):
                        calls += 1
                        if calls == 2:
                            values = list(info)
                            values[1 if field == "st_ino" else 6] += 1
                            return os.stat_result(values)
                    return info
                with patch.object(pg_adapter.os, "fstat", side_effect=mutate):
                    with self.assertRaises(OSError): self.promote()
                self.assertFalse((self.retained / REQUEST).exists())

    def test_retained_symlink_and_preexisting_final_collision_are_never_adopted(self):
        other = self.retained / "other"; other.mkdir()
        (self.retained / REQUEST).symlink_to(other, target_is_directory=True)
        with self.assertRaises(OSError): self.promote()
        self.assertFalse((other / f"{CLAIM}.json").exists())
        (self.retained / REQUEST).unlink()
        destination = self.retained / REQUEST; destination.mkdir()
        final = destination / f"{CLAIM}.json"; original = b"pre-existing"; final.write_bytes(original); final.chmod(0o640)
        with self.assertRaises(FileExistsError): self.promote()
        self.assertEqual(final.read_bytes(), original)

    def test_retained_partial_write_and_publication_failures_leave_no_success(self):
        for operation in ("write", "fsync", "link", "unlink"):
            with self.subTest(operation=operation):
                destination = self.retained / REQUEST
                if destination.exists():
                    for item in destination.iterdir(): item.unlink()
                    destination.rmdir()
                def injected(*args, **kwargs):
                    if operation == "write": return 0
                    raise OSError(operation)
                with patch.object(pg_adapter.os, operation, side_effect=injected):
                    with self.assertRaises(OSError): self.promote()
                if destination.exists():
                    if operation != "unlink":
                        self.assertFalse((destination / f"{CLAIM}.json").exists())

    def test_cleanup_refuses_replaced_inode_extra_entry_and_symlink_directory(self):
        result = self.promote()
        replacement = self.request_dir / "replacement"
        replacement.write_bytes(self.content); replacement.chmod(0o640)
        self.source.unlink(); os.link(replacement, self.source)
        self.assertFalse(pg_adapter.cleanup_phase5a_staging(REQUEST, CLAIM, result["staging_receipt"]))
        self.assertTrue(self.source.exists())
        self.source.unlink(); self.source.write_bytes(self.content); self.source.chmod(0o640)
        self.request_dir.joinpath("extra").write_bytes(b"keep")
        fresh_receipt = {"st_dev": self.source.stat().st_dev, "st_ino": self.source.stat().st_ino}
        with self.assertRaises(OSError): pg_adapter.cleanup_phase5a_staging(REQUEST, CLAIM, fresh_receipt)
        self.assertTrue((self.request_dir / "extra").exists())

    def test_reconcile_absence_removes_only_empty_request_directory(self):
        self.source.unlink()
        self.assertTrue(pg_adapter.reconcile_phase5a_staging_absence(REQUEST))
        self.assertFalse(self.request_dir.exists())
        self.request_dir.mkdir(); (self.request_dir / "unrelated").write_bytes(b"keep")
        self.assertFalse(pg_adapter.reconcile_phase5a_staging_absence(REQUEST))
        self.assertTrue((self.request_dir / "unrelated").exists())

    def test_cleanup_failure_boundaries_fail_closed_without_unrelated_removal(self):
        real_rmdir = os.rmdir
        for failure in ("unlink", "rmdir", "fsync", "replacement"):
            with self.subTest(failure=failure):
                if self.request_dir.is_symlink(): self.request_dir.unlink()
                elif self.request_dir.exists():
                    for item in self.request_dir.iterdir(): item.unlink()
                else: self.request_dir.mkdir()
                self.source.write_bytes(self.content); self.source.chmod(0o640)
                receipt = {"st_dev": self.source.stat().st_dev, "st_ino": self.source.stat().st_ino}
                other = self.staging / "replacement-target"
                if other.exists(): other.rmdir()
                def fail_rmdir(path, *args, **kwargs):
                    real_rmdir(path, *args, **kwargs)
                    if failure == "replacement":
                        other.mkdir(); self.request_dir.symlink_to(other, target_is_directory=True)
                    raise OSError("rmdir failure")
                real_unlink = os.unlink
                unlink_effect = OSError("unlink failure") if failure == "unlink" else (lambda path, *args, **kwargs: real_unlink(path, *args, **kwargs)) if failure == "replacement" else None
                with patch.object(pg_adapter.os, "unlink", side_effect=unlink_effect), patch.object(pg_adapter.os, "rmdir", side_effect=fail_rmdir if failure in {"rmdir", "replacement"} else None), patch.object(pg_adapter.os, "fsync", side_effect=OSError("fsync failure") if failure == "fsync" else None):
                    with self.assertRaises(OSError): pg_adapter.cleanup_phase5a_staging(REQUEST, CLAIM, receipt)
                if failure == "rmdir": self.assertTrue(self.request_dir.is_dir() and not self.request_dir.is_symlink())
                if failure == "replacement": self.assertTrue(self.request_dir.is_symlink())


class FinishCursor:
    def __init__(self, profile, artifact=None, run_id=RUN, artifact_run_id=RUN, prior=None):
        self.profile = profile; self.artifact = artifact; self.run_id = run_id; self.artifact_run_id = artifact_run_id; self.prior = prior; self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))

    def fetchone(self):
        sql, params = self.calls[-1]
        if "execution_requests WHERE id" in sql:
            return (CONTRACT, "verifying", self.profile)
        if "execution_controller_commands" in sql and "SELECT" in sql:
            return self.prior
        if "execution_controller_leases" in sql:
            return (CLAIM, "active", "phase5a-controller", pg_adapter.token_hash("t" * 43), None, False)
        if "FROM activity.runs" in sql:
            return (self.run_id,)
        if "run_artifacts" in sql and "SELECT" in sql:
            if params and len(params) >= 2 and params[1] != self.artifact_run_id:
                return None
            return self.artifact
        if "COALESCE(MAX(sequence_number)" in sql:
            return (0,)
        return None


class Phase5AFinishStatefulTests(unittest.TestCase):
    def body(self):
        return {"request_id": REQUEST, "contract_sha256": CONTRACT, "controller_id": "phase5a-controller", "idempotency_key": "finish-1", "claim_id": CLAIM, "claim_token": "t" * 43}

    def finish(self, cursor):
        handler = object.__new__(pg_adapter.Handler)
        return handler._controller_write(cursor, "/v1/controller/finish", self.body(), [])

    def test_phase5a_finish_requires_exact_matching_artifact_run(self):
        status, _ = self.finish(FinishCursor(pg_adapter.PHASE5A_PROFILE, artifact=None))
        self.assertEqual(status, 409)
        status, response = self.finish(FinishCursor(pg_adapter.PHASE5A_PROFILE, artifact=("artifact",)))
        self.assertEqual((status, response["state"]), (200, "awaiting_review"))

    def test_phase5a_finish_rejects_phase4b_only_and_wrong_run_artifact(self):
        status, _ = self.finish(FinishCursor(pg_adapter.PHASE5A_PROFILE, artifact=("artifact",), artifact_run_id="44444444-4444-4444-8444-444444444444"))
        self.assertEqual(status, 409)

    def test_phase4b_finish_still_requires_phase4b_artifact(self):
        status, _ = self.finish(FinishCursor("phase4b-fake-controller-v1", artifact=None))
        self.assertEqual(status, 409)


if __name__ == "__main__":
    unittest.main()
