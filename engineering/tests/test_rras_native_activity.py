import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / "rras_native" / (name + ".py"))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


a = module("activity")
p = module("prepare_profile")


class NativeActivityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.cmd("init", "-q")
        self.cmd("config", "user.name", "Test")
        self.cmd("config", "user.email", "test@example.invalid")
        (self.repo / "code.txt").write_text("base\n")
        self.cmd("add", "code.txt")
        self.cmd("commit", "-qm", "base")
        self.registry = self.root / "registry.json"
        self.registry.write_text(json.dumps({"schema_version": 1, "repositories": [
            {"repository_id": "demo", "path": str(self.repo), "enabled": True, "hermes_project": "demo"}]}))
        self.state = self.root / "records"
        self.record = a.admit(self.state, self.registry, "TASK-demo", "demo", "implement criterion")
        a.bind(self.state, "TASK-demo", "engineering", "task-1", "run-1")

    def cmd(self, *args):
        return subprocess.check_output(["git", "-C", str(self.repo), *args], stderr=subprocess.DEVNULL)

    def export(self):
        return a.export(self.state, "TASK-demo", self.repo)

    def test_admission_stable_after_head_changes_and_conflict_denied(self):
        (self.repo / "code.txt").write_text("change\n")
        self.cmd("commit", "-qam", "change")
        self.assertEqual(a.admit(self.state, self.registry, "TASK-demo", "demo", "implement criterion"), self.record)
        with self.assertRaises(a.RecordError):
            a.admit(self.state, self.registry, "TASK-demo", "demo", "different objective")

    def test_disabled_unknown_and_subdirectory_registry_denied(self):
        with self.assertRaises(a.RecordError):
            a.admit(self.state, self.registry, "next", "unknown", "objective")
        row = json.loads(self.registry.read_text())
        row["repositories"][0]["enabled"] = False
        self.registry.write_text(json.dumps(row))
        with self.assertRaises(a.RecordError):
            a.admit(self.state, self.registry, "next", "demo", "objective")
        sub = self.repo / "sub"
        sub.mkdir()
        with self.assertRaises(a.RecordError):
            a.canonical_repo(sub)

    def test_native_preview_triage_idempotent_and_no_execution(self):
        preview = a.preview(self.state, "TASK-demo")
        self.assertFalse(preview["execute"])
        self.assertIn("--triage", preview["argv"])
        self.assertIn("rras:TASK-demo", preview["argv"])
        self.assertIn("--project", preview["argv"])
        self.assertEqual(preview, a.preview(self.state, "TASK-demo"))

    def test_binding_cannot_silently_change_attempt(self):
        with self.assertRaises(a.RecordError):
            a.bind(self.state, "TASK-demo", "engineering", "task-1", "run-2")

    def test_patch_includes_staged_and_unstaged_and_export_is_idempotent(self):
        (self.repo / "code.txt").write_text("staged\n")
        self.cmd("add", "code.txt")
        (self.repo / "code.txt").write_text("unstaged\n")
        (self.repo / "untracked.txt").write_text("not automatically imported")
        result = self.export()
        self.assertEqual(result, self.export())
        manifest = a.verify_export(Path(result["path"]))
        self.assertIn(b"unstaged", (Path(result["path"]) / "changes.patch").read_bytes())
        self.assertIn(b"staged", (Path(result["path"]) / "index.patch").read_bytes())
        self.assertIn(b"untracked.txt", (Path(result["path"]) / "status.porcelain").read_bytes())
        self.assertFalse(result["database_indexed"])
        self.assertNotIn("untracked.txt", manifest["files"])

    def test_other_repo_worktree_denied(self):
        other = self.root / "other"
        subprocess.check_call(["git", "clone", "-q", str(self.repo), str(other)])
        with self.assertRaises(a.RecordError):
            a.export(self.state, "TASK-demo", other)

    def test_native_git_worktree_supported(self):
        wt = self.root / "worktree"
        self.cmd("worktree", "add", "-qb", "task-branch", str(wt))
        self.assertEqual(a.export(self.state, "TASK-demo", wt)["export_id"],
                         a.export(self.state, "TASK-demo", wt)["export_id"])

    def test_tampered_artifact_and_changed_review_refused(self):
        result = self.export()
        (Path(result["path"]) / "changes.patch").write_bytes(b"tampered")
        with self.assertRaises(a.RecordError):
            a.verify_export(Path(result["path"]))
        with self.assertRaises(a.RecordError):
            self.export()

    def test_review_requires_current_clean_committed_content(self):
        result = self.export()
        (self.repo / "code.txt").write_text("new\n")
        with self.assertRaises(a.RecordError):
            a.review(self.state, "TASK-demo", result["export_id"], "operator", "accepted")
        dirty = self.export()
        with self.assertRaises(a.RecordError):
            a.review(self.state, "TASK-demo", dirty["export_id"], "operator", "accepted")
        self.cmd("commit", "-qam", "change")
        clean = self.export()
        receipt = a.review(self.state, "TASK-demo", clean["export_id"], "operator", "accepted")
        self.assertFalse(receipt["remote_actions_authorized"])

    def test_symlink_log_duplicate_json_and_task_escape_refused(self):
        log = self.root / "log"
        log.symlink_to(self.repo / "code.txt")
        with self.assertRaises(a.RecordError):
            a.export(self.state, "TASK-demo", self.repo, [log])
        self.registry.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaises(a.RecordError):
            a.load(self.registry)
        with self.assertRaises(a.RecordError):
            a.task_path(self.state, "../escape")

    def test_profile_candidate_has_no_credentials_or_install(self):
        candidate = self.root / "candidate"
        manifest = p.prepare(candidate, "candidate-model")
        self.assertEqual(set(manifest["files"]), {"activity.py", "profile/config.yaml", "codex/config.toml", "activation-plan.json"})
        for name, expected in manifest["files"].items():
            self.assertEqual(a.digest((candidate / name).read_bytes()), expected)
        plan = json.loads((candidate / "activation-plan.json").read_text())
        self.assertFalse(plan["unattended_execution_enabled"])
        self.assertFalse(plan["codex_artifact_included"])
        with self.assertRaises(ValueError):
            p.prepare(candidate, "candidate-model")

    def test_external_diff_is_not_executed(self):
        marker = self.root / "external-was-run"
        program = self.root / "external"
        program.write_text('#!/bin/sh\ntouch "' + str(marker) + '"\n')
        program.chmod(0o700)
        self.cmd("config", "diff.external", str(program))
        (self.repo / "code.txt").write_text("change\n")
        self.export()
        self.assertFalse(marker.exists())








if __name__ == "__main__":
    unittest.main()
