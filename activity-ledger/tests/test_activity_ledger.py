from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import subprocess
from unittest.mock import Mock

from activity_ledger.ledger import ActivityLedger
from activity_ledger.allocator_policy import ManagedRootPolicy
from activity_ledger.adapter import InternalLedgerAdapter


class ActivityLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "activity.sqlite3"
        self.ledger = ActivityLedger(self.db_path)
        self.ledger.migrate()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_create_task_persists_canonical_task_key(self) -> None:
        task = self.ledger.create_task(
            task_key="TASK-20260916-001",
            title="Prototype ledger",
            description="Prove a durable task record.",
            origin_type="manual",
        )

        reloaded = self.ledger.get_task("TASK-20260916-001")

        self.assertEqual(task.task_key, "TASK-20260916-001")
        self.assertEqual(reloaded.task_key, "TASK-20260916-001")
        self.assertEqual(reloaded.state, "draft")

    def test_events_are_ordered_per_run(self) -> None:
        task = self.ledger.create_task(task_key="TASK-20260916-002", title="Events", description="", origin_type="manual")
        run_id = self.ledger.start_run(task.task_key, actor="hermes", source_interface="cli")
        self.ledger.append_event(run_id, "started", {"step": 1})
        self.ledger.append_event(run_id, "finished", {"step": 2})
        self.assertEqual([event["sequence_number"] for event in self.ledger.events(run_id)], [1, 2])

    def test_exclusive_writer_and_resource_collisions_are_rejected(self) -> None:
        task = self.ledger.create_task(task_key="TASK-20260916-003", title="Leases", description="", origin_type="manual")
        workspace_id = self.ledger.register_workspace(task.task_key, "/tmp/worktree", "codex/TASK-20260916-003", "base")
        self.ledger.acquire_writer(workspace_id, "hermes")
        with self.assertRaises(RuntimeError):
            self.ledger.acquire_writer(workspace_id, "other")
        self.ledger.register_resource("codex-worker-01", "codex-slot", "exclusive", 1)
        self.ledger.acquire_resources(task.task_key, ["codex-worker-01"], "hermes")
        with self.assertRaises(RuntimeError):
            self.ledger.acquire_resources(task.task_key, ["codex-worker-01"], "other")

    def test_projection_reports_drift_without_overwriting_canonical_state(self) -> None:
        task = self.ledger.create_task(task_key="TASK-20260916-004", title="Projection", description="", origin_type="manual")
        self.ledger.update_task_state(task.task_key, "ready")
        self.assertEqual(self.ledger.project_kanban(task.task_key, {"task_key": task.task_key, "state": "draft"})["status"], "drift")

    def test_allocator_creates_unique_disposable_worktree(self) -> None:
        source = Path(self.tempdir.name) / "source"
        source.mkdir()
        subprocess.run(["git", "init", "--initial-branch", "main"], cwd=source, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=source, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=source, check=True)
        (source / "README.md").write_text("prototype\n")
        subprocess.run(["git", "add", "."], cwd=source, check=True)
        subprocess.run(["git", "commit", "-m", "seed"], cwd=source, check=True, capture_output=True)
        self.ledger.create_task(task_key="TASK-20260916-005", title="Allocate", description="", origin_type="manual")
        path = self.ledger.allocate_worktree("TASK-20260916-005", source, Path(self.tempdir.name) / "tasks")
        self.assertTrue((path / ".git").exists())
        self.assertIn("codex/TASK-20260916-005", subprocess.check_output(["git", "branch", "--show-current"], cwd=path, text=True))

    def test_managed_policy_rejects_path_traversal_and_unregistered_repo(self) -> None:
        policy = ManagedRootPolicy({"prototype": "/srv/jarvis-dev/repos/prototype"})
        self.assertEqual(policy.task_root("prototype", "TASK-20260916-006"), "/srv/hermes-dev/jarvis/tasks/TASK-20260916-006")
        with self.assertRaises(ValueError): policy.task_root("prototype", "../escape")
        with self.assertRaises(ValueError): policy.task_root("unknown", "TASK-20260916-006")

    def test_managed_policy_accepts_only_canonical_task_keys(self) -> None:
        policy = ManagedRootPolicy({"prototype": "/srv/jarvis-dev/repos/prototype"})
        for task_key in ("TASK-20260916-001", "TASK-19990101-999"):
            self.assertTrue(policy.task_root("prototype", task_key).endswith(task_key))
        for task_key in (
            "TASK-2026-001",
            "task-20260916-001",
            "TASK-20260916-01",
            "TASK-20260916-1000",
            "TASK-20261340-001",
            "TASK-20260916-001/child",
            "",
        ):
            with self.subTest(task_key=task_key), self.assertRaises(ValueError):
                policy.task_root("prototype", task_key)

    def test_policy_rejects_absolute_and_normalized_path_escapes(self) -> None:
        policy = ManagedRootPolicy({"prototype": "/srv/jarvis-dev/repos/prototype"})
        for task_key in ("/tmp/escape", "../TASK-20260916-001", "TASK-20260916-001/../../escape"):
            with self.subTest(task_key=task_key), self.assertRaises(ValueError):
                policy.task_root("prototype", task_key)

    def test_allocator_rejects_historical_task_root_and_symlink_escape(self) -> None:
        policy = ManagedRootPolicy({"prototype": "/srv/jarvis-dev/repos/prototype"})
        managed_root = Path(self.tempdir.name) / "managed"
        historical = managed_root / "TASK-20240101-001"
        historical.mkdir(parents=True)
        with self.assertRaises(ValueError):
            policy.validate_task_root(historical, "TASK-20260916-007")

        outside = Path(self.tempdir.name) / "outside"
        outside.mkdir()
        link = managed_root / "TASK-20260916-008"
        managed_root.mkdir(exist_ok=True)
        link.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            policy.validate_task_root(link, "TASK-20260916-008")

    def test_allocator_rejects_duplicate_active_task_or_worktree(self) -> None:
        policy = ManagedRootPolicy({"prototype": "/srv/jarvis-dev/repos/prototype"})
        policy.register_allocation("TASK-20260916-009", "/managed/TASK-20260916-009/repo")
        with self.assertRaises(RuntimeError):
            policy.register_allocation("TASK-20260916-009", "/managed/other/repo")
        with self.assertRaises(RuntimeError):
            policy.register_allocation("TASK-20260916-010", "/managed/TASK-20260916-009/repo")

    def test_failed_acl_handoff_does_not_transfer_writer_lease(self) -> None:
        policy = ManagedRootPolicy({"prototype": "/srv/jarvis-dev/repos/prototype"})
        acl = Mock()
        acl.apply_handoff.side_effect = RuntimeError("setfacl failed")
        policy.register_allocation("TASK-20260916-011", "/managed/TASK-20260916-011/repo")
        policy.acquire_writer("TASK-20260916-011", "writer-a")
        with self.assertRaises(RuntimeError):
            policy.handoff_writer("TASK-20260916-011", "writer-a", "writer-b", acl)
        self.assertEqual(policy.active_writer("TASK-20260916-011"), "writer-a")
        acl.apply_handoff.assert_called_once()

    def test_internal_adapter_ingests_simulated_runner_events(self) -> None:
        adapter = InternalLedgerAdapter(self.ledger)
        run_id = adapter.start_simulated_run("TASK-20260916-012")
        adapter.ingest_runner_event(run_id, "runner_started", {"mode": "simulated"})
        adapter.ingest_runner_event(run_id, "runner_finished", {"exit_code": 0})
        self.assertEqual([event["event_type"] for event in self.ledger.events(run_id)], ["runner_started", "runner_finished"])


if __name__ == "__main__":
    unittest.main()
