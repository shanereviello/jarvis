from __future__ import annotations

import os
import posixpath
import re
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import repository_persistence as persistence

_TASK_KEY_RE = re.compile(r"^TASK-(\d{8})-(\d{3})$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_IDEMPOTENCY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}$")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_MAX_OUTPUT = 64 * 1024


class WorktreeAllocationError(RuntimeError):
    """Safe, bounded allocator failure without raw command output."""

    def __init__(self, classification: str, message: str, *, recovery_required: bool = False) -> None:
        super().__init__(message)
        self.classification = classification
        self.recovery_required = recovery_required


@dataclass(frozen=True)
class AllocationRequest:
    task_key: str
    repository_registration_id: str
    allocation_id: str
    worktree_id: str
    baseline_commit: str
    task_branch: str
    allocation_idempotency_key: str

    @classmethod
    def from_mapping(cls, value: object) -> "AllocationRequest":
        required = {
            "task_key", "repository_registration_id", "allocation_id", "worktree_id",
            "baseline_commit", "task_branch", "allocation_idempotency_key",
        }
        if not isinstance(value, dict) or set(value) != required:
            raise WorktreeAllocationError("work_order_rejected", "allocation request fields are not exact")
        task_key = value["task_key"]
        repository_id = value["repository_registration_id"]
        allocation_id = value["allocation_id"]
        worktree_id = value["worktree_id"]
        baseline = value["baseline_commit"]
        branch = value["task_branch"]
        key = value["allocation_idempotency_key"]
        if not isinstance(task_key, str) or _TASK_KEY_RE.fullmatch(task_key) is None:
            raise WorktreeAllocationError("work_order_rejected", "task identity is invalid")
        if not isinstance(repository_id, str) or _IDENTIFIER_RE.fullmatch(repository_id) is None:
            raise WorktreeAllocationError("work_order_rejected", "repository identity is invalid")
        if not isinstance(allocation_id, str) or str(_uuid(allocation_id)) != allocation_id:
            raise WorktreeAllocationError("work_order_rejected", "allocation identity is invalid")
        if not isinstance(worktree_id, str) or str(_uuid(worktree_id)) != worktree_id or worktree_id != allocation_id:
            raise WorktreeAllocationError("work_order_rejected", "worktree identity is invalid")
        if not isinstance(baseline, str) or _COMMIT_RE.fullmatch(baseline) is None:
            raise WorktreeAllocationError("work_order_rejected", "baseline identity is invalid")
        if not isinstance(branch, str) or not _valid_branch(branch):
            raise WorktreeAllocationError("work_order_rejected", "task branch is invalid")
        if not isinstance(key, str) or _IDEMPOTENCY_RE.fullmatch(key) is None:
            raise WorktreeAllocationError("work_order_rejected", "allocation idempotency identity is invalid")
        return cls(task_key, repository_id, allocation_id, worktree_id, baseline, branch, key)


@dataclass(frozen=True)
class HandoffDescriptor:
    task_key: str
    repository_registration_id: str
    allocation_id: str
    worktree_id: str
    worktree_path: str
    baseline_commit: str
    task_branch: str
    allocation_idempotency_key: str
    verified_clean_state: bool
    state: str

    def as_dict(self) -> dict[str, object]:
        return {
            "task_key": self.task_key,
            "repository_registration_id": self.repository_registration_id,
            "allocation_id": self.allocation_id,
            "worktree_id": self.worktree_id,
            "worktree_path": self.worktree_path,
            "baseline_commit": self.baseline_commit,
            "task_branch": self.task_branch,
            "allocation_idempotency_key": self.allocation_idempotency_key,
            "verified_clean_state": self.verified_clean_state,
            "state": self.state,
        }


def _uuid(value: str):
    from uuid import UUID
    return UUID(value)


def _valid_branch(value: str) -> bool:
    if (
        not value or value == "main" or value.startswith("/") or value.endswith("/")
        or value.endswith(".") or value.endswith(".lock") or ".." in value
        or "//" in value or "@{" in value or any(char in value for char in " ~^:?*[\\\x00")
        or any(ord(char) < 32 for char in value)
    ):
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,126}", value))


def _canonical_dir(value: Path, label: str) -> Path:
    if not value.is_absolute() or value.is_symlink() or not value.is_dir():
        raise WorktreeAllocationError("repository_binding_failed", f"{label} is not a canonical directory")
    resolved = value.resolve(strict=True)
    if resolved != value:
        raise WorktreeAllocationError("repository_binding_failed", f"{label} is not canonical")
    return resolved


def _beneath(path: Path, root: Path, label: str) -> None:
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise WorktreeAllocationError("repository_binding_failed", f"{label} escapes its approved root") from exc


class SecureWorktreeAllocator:
    """Internal, PostgreSQL-cursor-backed secure disposable worktree allocator."""

    def __init__(self, cursor: Any, *, worktree_root: str | Path, repository_root: str | Path, timeout_seconds: float = 10.0) -> None:
        self.cursor = cursor
        self.worktree_root = _canonical_dir(Path(worktree_root), "worktree root")
        self.repository_root = _canonical_dir(Path(repository_root), "repository root")
        self.timeout_seconds = timeout_seconds
        if not 0 < timeout_seconds <= 60:
            raise ValueError("allocator timeout is outside the bounded range")

    def allocate(self, request: AllocationRequest | dict[str, object]) -> HandoffDescriptor:
        request = request if isinstance(request, AllocationRequest) else AllocationRequest.from_mapping(request)
        self._lock_task(request.task_key)
        registration = persistence.get_repository_registration(self.cursor, request.repository_registration_id, require_enabled=True)
        repository = _canonical_dir(Path(registration.canonical_path), "registered repository")
        _beneath(repository, self.repository_root, "registered repository")
        task_id = self._task_id(request.task_key)
        existing_id = persistence.get_allocation_by_id(self.cursor, request.allocation_id)
        existing_key = persistence.get_allocation_by_idempotency_key(self.cursor, request.allocation_idempotency_key)
        if existing_id is not None or existing_key is not None:
            return self._replay(request, repository, task_id, existing_id, existing_key)

        primary = self._validate_repository(repository, request.baseline_commit)
        self._scan_features(repository, primary["git_dir"], request.baseline_commit)
        target = self._derived_worktree_path(request.task_key)
        if os.path.lexists(target):
            raise WorktreeAllocationError("repository_binding_failed", "derived worktree path already exists")
        if self._branch_exists(repository, request.task_branch):
            raise WorktreeAllocationError("repository_binding_failed", "task branch already exists")
        if any(item["path"] == str(target) for item in self._worktree_list(repository)):
            raise WorktreeAllocationError("repository_binding_failed", "worktree is already registered")

        task_root = target.parent
        task_root_created = False
        branch_created = False
        worktree_created = False
        persisted = False
        try:
            if not task_root.exists():
                task_root.mkdir(mode=0o750, parents=False)
                task_root_created = True
            self._run_git(repository, ["branch", "--no-track", "--", request.task_branch, request.baseline_commit])
            branch_created = True
            self._run_git(repository, ["worktree", "add", "--", str(target), request.task_branch])
            worktree_created = True
            self._verify_worktree(repository, target, request)
            binding = persistence.insert_allocation_binding(
                self.cursor,
                allocation_id=request.allocation_id,
                task_id=task_id,
                repository_registration_id=request.repository_registration_id,
                worktree_path=str(target),
                task_branch=request.task_branch,
                baseline_commit=request.baseline_commit,
                idempotency_key=request.allocation_idempotency_key,
            )
            persisted = True
            self._verify_primary_unchanged(repository, primary, request.baseline_commit)
            self._verify_worktree_inventory(repository, primary["worktrees"], target, request)
            if (
                binding.allocation_id != request.allocation_id
                or binding.task_id != task_id
                or binding.repository_registration_id != request.repository_registration_id
                or binding.worktree_path != str(target)
                or binding.task_branch != request.task_branch
                or binding.baseline_commit != request.baseline_commit
                or binding.idempotency_key != request.allocation_idempotency_key
            ):
                raise WorktreeAllocationError("repository_binding_failed", "persisted allocation does not match observed allocation", recovery_required=True)
            return self._descriptor(request, target, binding.state)
        except WorktreeAllocationError as exc:
            if not persisted:
                recovered = self._recover(repository, target, request, branch_created, worktree_created, task_root_created)
                if not recovered and not exc.recovery_required:
                    raise WorktreeAllocationError(exc.classification, str(exc), recovery_required=True) from exc
            raise
        except Exception as exc:
            recovered = True if persisted else self._recover(repository, target, request, branch_created, worktree_created, task_root_created)
            raise WorktreeAllocationError("allocation_failed", "allocation failed", recovery_required=not recovered) from exc

    def _replay(self, request: AllocationRequest, repository: Path, task_id: str, existing_id: Any, existing_key: Any) -> HandoffDescriptor:
        if existing_id is None or existing_key is None or existing_id != existing_key:
            raise WorktreeAllocationError("allocation_conflict", "allocation replay identities conflict")
        binding = existing_id
        if (
            binding.task_id != task_id or binding.repository_registration_id != request.repository_registration_id
            or binding.allocation_id != request.allocation_id or binding.worktree_path != str(self._derived_worktree_path(request.task_key))
            or binding.task_branch != request.task_branch or binding.baseline_commit != request.baseline_commit
            or binding.idempotency_key != request.allocation_idempotency_key
        ):
            raise WorktreeAllocationError("allocation_conflict", "allocation replay binding conflicts")
        primary = self._validate_repository(repository, request.baseline_commit)
        self._scan_features(repository, primary["git_dir"], request.baseline_commit)
        target = Path(binding.worktree_path)
        self._verify_worktree(repository, target, request)
        self._verify_primary_unchanged(repository, primary, request.baseline_commit)
        return self._descriptor(request, target, binding.state)

    def _lock_task(self, task_key: str) -> None:
        self.cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (task_key,))

    def _task_id(self, task_key: str) -> str:
        self.cursor.execute("SELECT id FROM activity.tasks WHERE task_key=%s", (task_key,))
        row = self.cursor.fetchone()
        if row is None:
            raise WorktreeAllocationError("repository_binding_failed", "task is not registered")
        return str(row[0])

    def _derived_worktree_path(self, task_key: str) -> Path:
        if _TASK_KEY_RE.fullmatch(task_key) is None:
            raise WorktreeAllocationError("work_order_rejected", "task identity is invalid")
        target = self.worktree_root / task_key / "repo"
        _beneath(target, self.worktree_root, "derived worktree")
        if target != target.parent / "repo":
            raise WorktreeAllocationError("repository_binding_failed", "derived worktree is not canonical")
        return target

    def _validate_repository(self, repository: Path, baseline: str) -> dict[str, Any]:
        if not _COMMIT_RE.fullmatch(baseline):
            raise WorktreeAllocationError("repository_binding_failed", "baseline identity is invalid")
        top = self._run_git(repository, ["rev-parse", "--show-toplevel"])[0]
        if Path(top) != repository:
            raise WorktreeAllocationError("repository_binding_failed", "repository identity mismatch")
        inside = self._run_git(repository, ["rev-parse", "--is-inside-work-tree"])[0]
        if inside != "true":
            raise WorktreeAllocationError("repository_binding_failed", "repository is not a worktree")
        git_dir_text = self._run_git(repository, ["rev-parse", "--git-dir"])[0]
        git_dir = Path(git_dir_text)
        if not git_dir.is_absolute():
            git_dir = (repository / git_dir).resolve(strict=True)
        if git_dir.is_symlink() or not git_dir.is_dir():
            raise WorktreeAllocationError("repository_binding_failed", "Git metadata boundary is unsafe")
        resolved = self._run_git(repository, ["rev-parse", "--verify", "--end-of-options", f"{baseline}^{{commit}}"])[0]
        if resolved != baseline:
            raise WorktreeAllocationError("repository_binding_failed", "baseline does not resolve exactly")
        if self._run_git(repository, ["cat-file", "-t", baseline])[0] != "commit":
            raise WorktreeAllocationError("repository_binding_failed", "baseline is not a commit")
        branch = self._run_git(repository, ["symbolic-ref", "--quiet", "--short", "HEAD"])[0]
        status = self._run_git(repository, ["status", "--porcelain", "--untracked-files=all"])[0]
        if not branch or status:
            raise WorktreeAllocationError("repository_binding_failed", "primary checkout is not clean")
        return {"git_dir": git_dir, "head": self._run_git(repository, ["rev-parse", "HEAD"])[0], "branch": branch, "status": status, "tree": self._run_git(repository, ["rev-parse", "HEAD^{tree}"])[0], "worktrees": self._worktree_list(repository)}

    def _scan_features(self, repository: Path, git_dir: Path, baseline: str) -> None:
        for root, dirs, files in os.walk(repository, followlinks=False):
            root_path = Path(root)
            dirs[:] = sorted(dirs)
            for name in list(dirs) + list(files):
                path = root_path / name
                info = os.lstat(path)
                if stat.S_ISLNK(info.st_mode) or not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
                    raise WorktreeAllocationError("repository_policy_violation", "repository contains unsafe filesystem entries")
                if name == ".git" and root_path != repository:
                    raise WorktreeAllocationError("repository_policy_violation", "nested repository detected")
        tree = self._run_git(repository, ["ls-tree", "-r", "-z", "--full-tree", baseline, "--"])[0]
        for record in tree.split("\x00"):
            if not record:
                continue
            header, path = record.split("\t", 1)
            mode = header.split(" ", 1)[0]
            if mode in {"160000", "120000"} or path in {".gitmodules", ".lfsconfig"}:
                raise WorktreeAllocationError("repository_policy_violation", "repository feature policy violation")
        try:
            attributes = self._run_git(repository, ["show", f"{baseline}:.gitattributes"])[0]
        except WorktreeAllocationError:
            attributes = ""
        if re.search(r"(?im)(^|\s)(filter|diff|merge|textconv|working-tree-encoding|ident)=", attributes):
            raise WorktreeAllocationError("repository_policy_violation", "external Git attribute behavior is prohibited")
        if (git_dir / "objects/info/alternates").exists() or (git_dir / "info/grafts").exists():
            raise WorktreeAllocationError("repository_policy_violation", "alternate or graft object storage is prohibited")
        if (git_dir / "info/sparse-checkout").exists() or self._config_values(repository, "core.sparseCheckout"):
            raise WorktreeAllocationError("repository_policy_violation", "sparse checkout is prohibited")
        if self._run_git(repository, ["replace", "-l"])[0]:
            raise WorktreeAllocationError("repository_policy_violation", "replace refs are prohibited")
        for hook in (git_dir / "hooks").glob("*") if (git_dir / "hooks").is_dir() else ():
            if hook.name.endswith(".sample"):
                continue
            raise WorktreeAllocationError("repository_policy_violation", "active Git hooks are prohibited")
        config_keys = self._run_git(repository, ["config", "--local", "--no-includes", "--null", "--list"])[0].split("\x00")
        forbidden_prefixes = ("include", "credential.", "diff.", "difftool.", "filter.", "fsmonitor.", "core.fsmonitor", "merge.")
        if any(any(item.startswith(prefix) for prefix in forbidden_prefixes) for item in config_keys if item):
            raise WorktreeAllocationError("repository_policy_violation", "unsafe Git configuration is prohibited")

    def _config_values(self, repository: Path, key: str) -> bool:
        result = self._run_git(repository, ["config", "--local", "--no-includes", "--get", key], allow_failure=True)
        return result[0].lower() in {"true", "yes", "on", "1"}

    def _branch_exists(self, repository: Path, branch: str) -> bool:
        return self._run_git(repository, ["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"], allow_failure=True, return_status=True)[1] == 0

    def _worktree_list(self, repository: Path) -> list[dict[str, str]]:
        output = self._run_git(repository, ["worktree", "list", "--porcelain"])[0]
        entries: list[dict[str, str]] = []
        current: dict[str, str] = {}
        for line in output.splitlines():
            if not line:
                if current:
                    entries.append(current)
                    current = {}
                continue
            key, _, value = line.partition(" ")
            if key == "worktree":
                current["path"] = value
            elif key in {"HEAD", "branch"}:
                current[key] = value.removeprefix("refs/heads/") if key == "branch" else value
        if current:
            entries.append(current)
        return entries

    def _verify_worktree(self, repository: Path, target: Path, request: AllocationRequest) -> None:
        if target.is_symlink() or not target.is_dir() or target.resolve() != target:
            raise WorktreeAllocationError("repository_binding_failed", "allocated worktree boundary is unsafe")
        if Path(self._run_git(target, ["rev-parse", "--show-toplevel"])[0]) != target:
            raise WorktreeAllocationError("repository_binding_failed", "allocated worktree identity mismatch")
        repository_git_dir = self._run_git(repository, ["rev-parse", "--git-dir"])[0]
        repository_git_dir_path = Path(repository_git_dir)
        if not repository_git_dir_path.is_absolute():
            repository_git_dir_path = (repository / repository_git_dir_path).resolve()
        worktree_common_dir = self._run_git(target, ["rev-parse", "--git-common-dir"])[0]
        worktree_common_dir_path = Path(worktree_common_dir)
        if not worktree_common_dir_path.is_absolute():
            worktree_common_dir_path = (target / worktree_common_dir_path).resolve()
        if worktree_common_dir_path != repository_git_dir_path:
            raise WorktreeAllocationError("allocation_conflict", "worktree is bound to a different repository")
        if self._run_git(target, ["symbolic-ref", "--quiet", "--short", "HEAD"])[0] != request.task_branch:
            raise WorktreeAllocationError("allocation_conflict", "allocated branch identity mismatch")
        if self._run_git(target, ["rev-parse", "HEAD"])[0] != request.baseline_commit:
            raise WorktreeAllocationError("allocation_conflict", "allocated baseline identity mismatch")
        if self._run_git(target, ["status", "--porcelain", "--untracked-files=all"])[0]:
            raise WorktreeAllocationError("repository_binding_failed", "allocated worktree is not clean")
        entries = [item for item in self._worktree_list(repository) if item.get("path") == str(target)]
        if len(entries) != 1 or entries[0].get("branch") != request.task_branch or entries[0].get("HEAD") != request.baseline_commit:
            raise WorktreeAllocationError("repository_binding_failed", "Git worktree registration is not exact")

    def _verify_primary_unchanged(self, repository: Path, snapshot: dict[str, Any], baseline: str) -> None:
        current = self._validate_repository(repository, baseline)
        for key in ("head", "branch", "status", "tree"):
            if current[key] != snapshot[key]:
                raise WorktreeAllocationError("repository_binding_failed", "primary checkout changed")

    def _verify_worktree_inventory(self, repository: Path, before: list[dict[str, str]], target: Path, request: AllocationRequest) -> None:
        after = self._worktree_list(repository)
        added = [entry for entry in after if entry not in before]
        if len(added) != 1 or added[0].get("path") != str(target) or added[0].get("branch") != request.task_branch:
            raise WorktreeAllocationError("repository_binding_failed", "unrelated worktree inventory changed")

    def _descriptor(self, request: AllocationRequest, target: Path, state: str) -> HandoffDescriptor:
        return HandoffDescriptor(request.task_key, request.repository_registration_id, request.allocation_id, request.worktree_id, str(target), request.baseline_commit, request.task_branch, request.allocation_idempotency_key, True, state)

    def _recover(self, repository: Path, target: Path, request: AllocationRequest, branch_created: bool, worktree_created: bool, task_root_created: bool) -> bool:
        try:
            if worktree_created and target.exists():
                self._verify_worktree(repository, target, request)
                self._run_git(repository, ["worktree", "remove", "--force", "--", str(target)])
            if branch_created and not target.exists() and not any(item.get("path") == str(target) for item in self._worktree_list(repository)) and self._branch_points_to(repository, request.task_branch, request.baseline_commit):
                self._run_git(repository, ["branch", "-d", "--", request.task_branch])
            if task_root_created and target.parent.is_dir() and not any(target.parent.iterdir()):
                target.parent.rmdir()
            return not target.exists() and not self._branch_exists(repository, request.task_branch)
        except Exception:
            return False

    def _branch_points_to(self, repository: Path, branch: str, baseline: str) -> bool:
        return self._run_git(repository, ["rev-parse", "--verify", f"refs/heads/{branch}"])[0] == baseline

    def _run_git(self, cwd: Path, arguments: list[str], *, allow_failure: bool = False, return_status: bool = False) -> tuple[str, int] | tuple[str, int]:
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": "/nonexistent",
            "LANG": "C",
            "LC_ALL": "C",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_OPTIONAL_LOCKS": "0",
        }
        command = [
            "git", "--no-pager", "-c", "core.hooksPath=/dev/null", "-c", "credential.helper=",
            "-c", "core.fsmonitor=false", "-c", "core.autocrlf=false", "-c", "core.safecrlf=false",
            "-c", "diff.external=", *arguments,
        ]
        try:
            completed = subprocess.run(command, cwd=cwd, env=env, shell=False, capture_output=True, text=True, timeout=self.timeout_seconds, check=False)
        except subprocess.TimeoutExpired as exc:
            raise WorktreeAllocationError("git_timeout", "Git operation timed out", recovery_required=True) from exc
        stdout = completed.stdout[:_MAX_OUTPUT].rstrip("\n")
        if completed.returncode != 0 and not allow_failure:
            raise WorktreeAllocationError("git_failed", "Git operation failed", recovery_required=True)
        return (stdout, completed.returncode)
