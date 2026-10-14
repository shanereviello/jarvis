from __future__ import annotations

import re
from datetime import date
from pathlib import Path, PurePosixPath
from threading import RLock

_TASK_KEY = re.compile(r"^TASK-(\d{8})-(\d{3})$")
_DEFAULT_MANAGED_ROOT = PurePosixPath("/srv/hermes-dev/jarvis/tasks")


class ManagedRootPolicy:
    """Validation boundary for the future root-owned allocator service."""

    def __init__(self, repositories: dict[str, str], managed_root: str | Path = str(_DEFAULT_MANAGED_ROOT)) -> None:
        self.repositories = dict(repositories)
        self.managed_root = PurePosixPath(managed_root)
        self._allocations: dict[str, str] = {}
        self._writers: dict[str, str] = {}
        self._lock = RLock()

    def task_root(self, repository_id: str, task_key: str) -> str:
        if repository_id not in self.repositories:
            raise ValueError("unregistered repository")
        match = _TASK_KEY.fullmatch(task_key)
        if match is None:
            raise ValueError("invalid canonical task key")
        try:
            date.fromisoformat(match.group(1))
        except ValueError as exc:
            raise ValueError("invalid canonical task key") from exc
        candidate = self.managed_root / task_key
        if candidate.parent != self.managed_root or not candidate.is_absolute():
            raise ValueError("managed-root escape")
        return str(candidate)

    def validate_task_root(self, path: str | Path, task_key: str) -> Path:
        if _TASK_KEY.fullmatch(task_key) is None:
            raise ValueError("invalid canonical task key")
        expected = Path(self.managed_root) / task_key
        candidate = Path(path)
        if not candidate.is_absolute() or candidate.parent != expected.parent or candidate.name != task_key:
            raise ValueError("historical or unmanaged task root")
        if candidate.is_symlink() or candidate.resolve(strict=False).parent != expected.parent.resolve(strict=False):
            raise ValueError("symlink escape")
        return candidate

    def register_allocation(self, task_key: str, worktree_path: str) -> None:
        with self._lock:
            if task_key in self._allocations:
                raise RuntimeError(f"active allocation already exists for {task_key}")
            if worktree_path in self._allocations.values():
                raise RuntimeError(f"active worktree already exists: {worktree_path}")
            self._allocations[task_key] = worktree_path

    def acquire_writer(self, task_key: str, owner: str) -> None:
        with self._lock:
            if task_key not in self._allocations:
                raise KeyError(task_key)
            if task_key in self._writers:
                raise RuntimeError(f"writer lease held by {self._writers[task_key]}")
            self._writers[task_key] = owner

    def active_writer(self, task_key: str) -> str | None:
        with self._lock:
            return self._writers.get(task_key)

    def handoff_writer(self, task_key: str, prior_writer: str, next_writer: str, acl_handoff: object) -> None:
        """Transfer ownership only after the complete filesystem handoff succeeds.

        ``acl_handoff.apply_handoff`` owns the exclusive lock, writer quiesce/run
        checks, ownership normalization, ACL updates, and effective-ACL checks.
        The in-memory lease is intentionally changed last.
        """
        with self._lock:
            if self._writers.get(task_key) != prior_writer:
                raise RuntimeError("prior writer does not hold the active lease")
            apply_handoff = getattr(acl_handoff, "apply_handoff")
            apply_handoff(task_key, prior_writer, next_writer)
            self._writers[task_key] = next_writer

    @staticmethod
    def handoff_template() -> tuple[str, ...]:
        return (
            "acquire exclusive task/worktree handoff lock",
            "stop or quiesce current writer and verify no active run owns writer lease",
            "chown -R root:jarvis-dev <task-root>",
            "setfacl -R -x u:<prior-writer> <task-root>; reset directory defaults",
            "setfacl -R -m u:<next-writer>:rw- <task-root-files>",
            "setfacl -R -m u:<next-writer>:rwx <task-root-directories>",
            "verify effective masks, ownership, and jarvis-dev read/traverse access",
            "transfer activity-ledger lease only after filesystem verification",
        )
