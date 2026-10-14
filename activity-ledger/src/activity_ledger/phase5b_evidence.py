from __future__ import annotations

import hashlib
import json
import os
import selectors
import stat
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .workflow_registry import WorkflowRegistry, canonical_json

MAX_RESULT_BYTES = 131072
MAX_PATCH_BYTES = 65536


class EvidenceCustodyError(RuntimeError):
    def __init__(self, classification: str, message: str = "Phase 5B evidence custody failed") -> None:
        super().__init__(message)
        self.classification = classification


@dataclass(frozen=True)
class RetainedArtifact:
    artifact_type: str
    artifact_id: str
    retained_path: str
    sha256: str
    size_bytes: int
    duplicate: bool = False


@dataclass(frozen=True)
class CustodyResult:
    result: RetainedArtifact
    patch: RetainedArtifact | None
    staging_cleaned: bool


@dataclass
class InProcessEvidencePersistence:
    registrations: dict[tuple[str, str, int, str], RetainedArtifact] = field(default_factory=dict)


def _read_regular(path: Path, maximum: int) -> tuple[bytes, tuple[int, int]]:
    fd = -1
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC)
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > maximum:
            raise EvidenceCustodyError("evidence_invalid", "evidence is not a bounded regular file")
        chunks: list[bytes] = []
        total = 0
        while total <= maximum:
            chunk = os.read(fd, min(8192, maximum + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
        after = os.fstat(fd)
        identity = (before.st_dev, before.st_ino)
        data = b"".join(chunks)
        if identity != (after.st_dev, after.st_ino) or len(data) != after.st_size or total > maximum:
            raise EvidenceCustodyError("evidence_changed", "evidence changed while reading")
        return data, identity
    except EvidenceCustodyError:
        raise
    except OSError as exc:
        raise EvidenceCustodyError("evidence_unavailable") from exc
    finally:
        if fd >= 0:
            os.close(fd)


def _write_absent_only(path: Path, content: bytes) -> tuple[bool, tuple[int, int]]:
    path.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
    try:
        existing, identity = _read_regular(path, max(len(content), 131072))
    except EvidenceCustodyError as exc:
        if exc.classification != "evidence_unavailable":
            raise
    else:
        if existing != content:
            raise EvidenceCustodyError("artifact_conflict", "retained artifact bytes conflict")
        return True, identity
    fd = -1
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o640)
        written = 0
        while written < len(content):
            count = os.write(fd, content[written:])
            if count <= 0:
                raise OSError("short evidence write")
            written += count
        os.fsync(fd)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size != len(content):
            raise EvidenceCustodyError("evidence_changed", "retained artifact metadata is invalid")
        return False, (info.st_dev, info.st_ino)
    except FileExistsError:
        existing, identity = _read_regular(path, max(len(content), 131072))
        if existing != content:
            raise EvidenceCustodyError("artifact_conflict", "retained artifact bytes conflict")
        return True, identity
    except EvidenceCustodyError:
        raise
    except OSError as exc:
        raise EvidenceCustodyError("evidence_publication_failed") from exc
    finally:
        if fd >= 0:
            os.close(fd)


def _cleanup_exact(path: Path, identity: tuple[int, int]) -> bool:
    fd = -1
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC)
        info = os.fstat(fd)
        if (info.st_dev, info.st_ino) != identity:
            raise EvidenceCustodyError("cleanup_conflict", "staging identity changed")
        os.close(fd)
        fd = -1
        os.unlink(path)
        return not path.exists()
    except FileNotFoundError:
        return True
    except EvidenceCustodyError:
        raise
    except OSError as exc:
        raise EvidenceCustodyError("cleanup_failed") from exc
    finally:
        if fd >= 0:
            os.close(fd)


def _bounded_git(worktree: Path, env: dict[str, str], arguments: tuple[str, ...], maximum: int = 1024 * 1024) -> bytes:
    try:
        process = subprocess.Popen(["git", "--no-pager", "-c", "core.hooksPath=/dev/null", *arguments], cwd=worktree, env=env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, shell=False, start_new_session=True)
    except OSError as exc:
        raise EvidenceCustodyError("evidence_binding_conflict", "trusted Git verification failed") from exc
    assert process.stdout is not None
    fd = process.stdout.fileno()
    os.set_blocking(fd, False)
    selector = selectors.DefaultSelector()
    selector.register(fd, selectors.EVENT_READ)
    output = bytearray()
    deadline = time.monotonic() + 10
    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise EvidenceCustodyError("evidence_binding_conflict", "trusted Git verification timed out")
            for key, _ in selector.select(min(0.05, remaining)):
                while True:
                    try:
                        chunk = os.read(key.fd, min(8192, maximum + 1 - len(output)))
                    except BlockingIOError:
                        break
                    if not chunk:
                        selector.unregister(key.fd)
                        break
                    output.extend(chunk)
                    if len(output) > maximum:
                        raise EvidenceCustodyError("evidence_binding_conflict", "trusted Git output exceeded the bound")
        if process.wait(timeout=max(0.01, deadline - time.monotonic())) != 0:
            raise EvidenceCustodyError("evidence_binding_conflict", "trusted Git verification failed")
        return bytes(output)
    except (EvidenceCustodyError, OSError, subprocess.SubprocessError):
        try:
            process.kill()
        except ProcessLookupError:
            pass
        process.wait(timeout=1)
        raise
    finally:
        selector.close()
        process.stdout.close()


class Phase5BEvidenceCustodian:
    """Reusable adapter-bound custody; persistence is injectable for restart/recovery tests."""

    def __init__(self, retained_root: Path, persistence: InProcessEvidencePersistence | None = None) -> None:
        self.retained_root = Path(retained_root)
        self.persistence = persistence or InProcessEvidencePersistence()
        self.registrations = self.persistence.registrations
        self.fail_registration_for: set[str] = set()
        self.fail_cleanup = False

    def retain_success(self, *, result_path: Path, patch_path: Path, order: dict[str, Any], result: dict[str, Any], worktree_path: Path | None = None) -> CustodyResult:
        try:
            self._validate_result_binding(order, result)
        except EvidenceCustodyError:
            raise
        except (KeyError, TypeError) as exc:
            raise EvidenceCustodyError("evidence_binding_conflict", "admitted work binding is incomplete") from exc
        try:
            criteria = {item["criterion_id"] for item in order["normalized_contract"]["acceptance_criteria"]}
            WorkflowRegistry.validate_phase5b_result_v2(result, criteria)
        except Exception as exc:
            raise EvidenceCustodyError("evidence_invalid", "result semantic validation failed") from exc
        result_bytes, result_identity = _read_regular(result_path, MAX_RESULT_BYTES)
        unsigned = {key: value for key, value in result.items() if key != "result_sha256"}
        if result_bytes != canonical_json(result) or hashlib.sha256(canonical_json(unsigned)).hexdigest() != result["result_sha256"]:
            raise EvidenceCustodyError("evidence_invalid", "result canonical bytes or digest mismatch")
        patch_descriptor = result["patch_descriptor"]
        patch_bytes, patch_identity = _read_regular(patch_path, MAX_PATCH_BYTES)
        if len(patch_bytes) != patch_descriptor["size_bytes"] or hashlib.sha256(patch_bytes).hexdigest() != patch_descriptor["sha256"]:
            raise EvidenceCustodyError("evidence_invalid", "patch digest or size mismatch")
        if patch_descriptor["relative_name"] != patch_path.name:
            raise EvidenceCustodyError("evidence_invalid", "patch descriptor path mismatch")
        if worktree_path is None:
            raise EvidenceCustodyError("evidence_invalid", "trusted worktree boundary is required")
        self._verify_host_state(Path(worktree_path), order, result, patch_bytes)
        binding = (result["request_id"], result["run_id"], result["attempt_number"])
        result_record = self._retain("phase5b_codex_executor_result", "result.json", result_bytes, binding)
        patch_record = self._retain("phase5b_codex_patch", "patch.diff", patch_bytes, binding)
        if self.fail_cleanup:
            raise EvidenceCustodyError("cleanup_failed")
        if not _cleanup_exact(result_path, result_identity) or not _cleanup_exact(patch_path, patch_identity):
            raise EvidenceCustodyError("cleanup_failed")
        return CustodyResult(result_record, patch_record, True)

    def reconcile_success(self, *, order: dict[str, Any], result_record: RetainedArtifact, patch_record: RetainedArtifact, worktree_path: Path) -> CustodyResult:
        """Revalidate retained success evidence without staging, transport, or mutation."""
        result_bytes = self.readback(result_record)
        patch_bytes = self.readback(patch_record)
        try:
            result = json.loads(result_bytes.decode("utf-8"))
            criteria = {item["criterion_id"] for item in order["normalized_contract"]["acceptance_criteria"]}
            WorkflowRegistry.validate_phase5b_result_v2(result, criteria)
        except Exception as exc:
            raise EvidenceCustodyError("evidence_invalid", "retained result semantic validation failed") from exc
        self._validate_result_binding(order, result)
        if result_bytes != canonical_json(result):
            raise EvidenceCustodyError("registration_conflict", "retained result is not canonical")
        unsigned = {key: value for key, value in result.items() if key != "result_sha256"}
        if hashlib.sha256(canonical_json(unsigned)).hexdigest() != result["result_sha256"]:
            raise EvidenceCustodyError("registration_conflict", "retained result digest does not match")
        descriptor = result["patch_descriptor"]
        if patch_record.artifact_type != descriptor["artifact_type"] or patch_record.size_bytes != len(patch_bytes) or patch_record.sha256 != hashlib.sha256(patch_bytes).hexdigest():
            raise EvidenceCustodyError("registration_conflict", "retained patch registration does not match descriptor")
        self._verify_host_state(Path(worktree_path), order, result, patch_bytes)
        return CustodyResult(result_record, patch_record, True)

    @staticmethod
    def _validate_result_binding(order: dict[str, Any], result: dict[str, Any]) -> None:
        expected = {
            "request_id": order["request_id"], "claim_id": order["claim_id"], "run_id": order["run_id"],
            "attempt_number": order["attempt_number"], "contract_sha256": order["contract_sha256"],
            "repository_registration_id": order["repository_registration_id"], "allocation_id": order["allocation_id"],
            "worktree_id": order["worktree_id"], "baseline_commit": order["baseline_commit"],
            "task_branch": order["task_branch"], "executor_profile": order["executor_profile"],
            "model_profile": order["model_profile"], "validation_plan_id": order["validation_plan_id"],
        }
        if any(result.get(key) != value for key, value in expected.items()):
            raise EvidenceCustodyError("evidence_binding_conflict", "result is not bound to admitted work")

    @staticmethod
    def _verify_host_state(worktree: Path, order: dict[str, Any], result: dict[str, Any], patch_bytes: bytes | None = None) -> None:
        if not worktree.is_absolute() or worktree.is_symlink() or not worktree.is_dir() or worktree.resolve() != worktree:
            raise EvidenceCustodyError("evidence_binding_conflict", "worktree boundary is not trusted")
        env = {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "LANG": "C", "LC_ALL": "C", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull, "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0"}

        def git(*args: str) -> bytes:
            return _bounded_git(worktree, env, args)

        commit = result["commit_descriptor"]
        if git("symbolic-ref", "--quiet", "--short", "HEAD").decode().strip() != order["task_branch"]:
            raise EvidenceCustodyError("evidence_binding_conflict", "task branch does not match admitted work")
        if git("rev-parse", "HEAD").decode().strip() != commit["commit_id"]:
            raise EvidenceCustodyError("evidence_binding_conflict", "task commit does not match result")
        if git("rev-parse", "HEAD^").decode().strip() != order["baseline_commit"] or commit["parent_commit_id"] != order["baseline_commit"]:
            raise EvidenceCustodyError("evidence_binding_conflict", "commit parent does not match baseline")
        if git("status", "--porcelain", "--untracked-files=all"):
            raise EvidenceCustodyError("evidence_binding_conflict", "task worktree is not clean")
        tree = hashlib.sha256(git("ls-tree", "-r", "-z", commit["commit_id"])).hexdigest()
        if tree != commit["tree_sha256"]:
            raise EvidenceCustodyError("evidence_binding_conflict", "commit tree does not match result")
        raw = git("diff", "--name-status", "--no-renames", commit["parent_commit_id"], commit["commit_id"], "--").decode()
        actual: list[dict[str, Any]] = []
        for line in raw.splitlines():
            status, _, relative = line.partition("\t")
            if status not in {"A", "M", "D"} or not relative or relative == ".git":
                raise EvidenceCustodyError("evidence_binding_conflict", "changed-file manifest is unsafe")
            if status == "D":
                data = b""
            else:
                try:
                    data = _bounded_git(worktree, env, ("show", f"{commit['commit_id']}:{relative}"), 8192)
                except EvidenceCustodyError as exc:
                    raise EvidenceCustodyError("evidence_binding_conflict", "changed-file verification failed") from exc
            actual.append({"relative_path": relative, "status": {"A": "added", "M": "modified", "D": "deleted"}[status], "sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data), "media_type": "text/plain" if b"\x00" not in data else "application/octet-stream"})
        actual.sort(key=lambda item: item["relative_path"])
        if actual != result["changed_file_manifest"] or commit["changed_file_count"] != len(actual):
            raise EvidenceCustodyError("evidence_binding_conflict", "changed-file manifest does not match commit")
        if patch_bytes is not None:
            expected_patch = git("diff", "--binary", "--no-ext-diff", commit["parent_commit_id"], commit["commit_id"], "--")
            if patch_bytes != expected_patch or hashlib.sha256(patch_bytes).hexdigest() != result["patch_descriptor"]["sha256"] or len(patch_bytes) != result["patch_descriptor"]["size_bytes"]:
                raise EvidenceCustodyError("evidence_binding_conflict", "retained patch does not match commit")

    def retain_failure(self, *, result_path: Path, order: dict[str, Any], result: dict[str, Any]) -> RetainedArtifact:
        try:
            self._validate_result_binding(order, result)
            WorkflowRegistry.validate_phase5b_result_v2(result)
        except EvidenceCustodyError:
            raise
        except Exception as exc:
            raise EvidenceCustodyError("evidence_invalid", "failure semantic validation failed") from exc
        content, identity = _read_regular(result_path, 32768)
        unsigned = {key: value for key, value in result.items() if key != "result_sha256"}
        if content != canonical_json(result) or hashlib.sha256(canonical_json(unsigned)).hexdigest() != result["result_sha256"]:
            raise EvidenceCustodyError("evidence_invalid")
        record = self._retain("phase5b_codex_failure", "failure.json", content, (result["request_id"], result["run_id"], result["attempt_number"]))
        if not _cleanup_exact(result_path, identity):
            raise EvidenceCustodyError("cleanup_failed")
        return record

    def read_failure_staging(self, result_path: Path) -> dict[str, Any]:
        """Read an executor failure receipt with the bounded evidence limit."""
        content, _ = _read_regular(result_path, 32768)
        try:
            value = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise EvidenceCustodyError("evidence_invalid", "failure result is not canonical JSON") from exc
        if not isinstance(value, dict):
            raise EvidenceCustodyError("evidence_invalid", "failure result must be an object")
        return value

    def reconcile_failure(self, *, order: dict[str, Any], failure_record: RetainedArtifact) -> RetainedArtifact:
        """Verify a retained failure receipt without staging, transport, or mutation."""
        content = self.readback(failure_record)
        try:
            result = json.loads(content.decode("utf-8"))
            self._validate_result_binding(order, result)
            WorkflowRegistry.validate_phase5b_result_v2(result)
        except EvidenceCustodyError:
            raise
        except Exception as exc:
            raise EvidenceCustodyError("registration_conflict", "retained failure result is invalid") from exc
        if failure_record.artifact_type != "phase5b_codex_failure" or content != canonical_json(result):
            raise EvidenceCustodyError("registration_conflict", "retained failure result is not canonical")
        unsigned = {key: value for key, value in result.items() if key != "result_sha256"}
        if hashlib.sha256(canonical_json(unsigned)).hexdigest() != result.get("result_sha256"):
            raise EvidenceCustodyError("registration_conflict", "retained failure digest does not match")
        return failure_record

    def readback(self, artifact: RetainedArtifact) -> bytes:
        content, _ = _read_regular(Path(artifact.retained_path), max(artifact.size_bytes, 131072))
        if len(content) != artifact.size_bytes or hashlib.sha256(content).hexdigest() != artifact.sha256:
            raise EvidenceCustodyError("registration_conflict", "retained artifact readback mismatch")
        return content

    def _retain(self, artifact_type: str, filename: str, content: bytes, binding: tuple[str, str, int]) -> RetainedArtifact:
        key = (*binding, artifact_type)
        if artifact_type in self.fail_registration_for:
            raise EvidenceCustodyError("registration_failed")
        retained_path = self.retained_root / binding[0] / binding[1] / str(binding[2]) / filename
        digest = hashlib.sha256(content).hexdigest()
        duplicate, _ = _write_absent_only(retained_path, content)
        artifact_id = f"{artifact_type}:{binding[0]}:{binding[1]}:{binding[2]}"
        record = RetainedArtifact(artifact_type, artifact_id, str(retained_path), digest, len(content), duplicate)
        prior = self.registrations.get(key)
        if prior is not None and (prior.sha256 != digest or prior.size_bytes != len(content) or prior.retained_path != record.retained_path):
            raise EvidenceCustodyError("registration_conflict")
        self.registrations[key] = record
        self.readback(record)
        return record
