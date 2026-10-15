from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_IDEMPOTENCY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}$")
_SHA1_RE = re.compile(r"^[0-9a-f]{40}$")


class RepositoryPersistenceError(ValueError):
    pass


class RepositoryNotFound(RepositoryPersistenceError):
    pass


class RepositoryDisabled(RepositoryPersistenceError):
    pass


class AllocationConflict(RepositoryPersistenceError):
    pass


@dataclass(frozen=True)
class RepositoryRegistration:
    repository_registration_id: str
    canonical_path: str
    enabled: bool
    created_at: datetime | None
    updated_at: datetime | None


@dataclass(frozen=True)
class AllocationBinding:
    allocation_id: str
    task_id: str
    repository_registration_id: str
    worktree_path: str
    task_branch: str
    baseline_commit: str
    idempotency_key: str
    state: str
    created_at: datetime | None
    updated_at: datetime | None


def _canonical_uuid(value: object, name: str) -> str:
    try:
        canonical = str(UUID(value)) if isinstance(value, str) else ""
    except ValueError:
        canonical = ""
    if canonical != value:
        raise RepositoryPersistenceError(f"invalid {name}")
    return canonical


def _repository_id(value: object) -> str:
    if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
        raise RepositoryPersistenceError("invalid repository registration identity")
    return value


def _canonical_path(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.startswith("/") or "\\" in value or any(ord(char) < 32 for char in value):
        raise RepositoryPersistenceError(f"invalid {name}")
    if value == "/" or value.endswith("/") or "//" in value:
        raise RepositoryPersistenceError(f"noncanonical {name}")
    if any(part in {"", ".", ".."} for part in value.split("/")[1:]) or posixpath.normpath(value) != value:
        raise RepositoryPersistenceError(f"noncanonical {name}")
    if value.startswith(("/proc/", "/sys/", "/dev/", "/run/")):
        raise RepositoryPersistenceError(f"prohibited {name}")
    return value


def _branch(value: object) -> str:
    if not isinstance(value, str) or not value or value == "main" or value.startswith("/") or "\\" in value or "\x00" in value or any(ord(char) < 32 for char in value) or len(value) > 127:
        raise RepositoryPersistenceError("invalid task branch")
    return value


def _commit(value: object) -> str:
    if not isinstance(value, str) or _SHA1_RE.fullmatch(value) is None:
        raise RepositoryPersistenceError("invalid baseline commit")
    return value


def _key(value: object) -> str:
    if not isinstance(value, str) or _IDEMPOTENCY_RE.fullmatch(value) is None:
        raise RepositoryPersistenceError("invalid allocation idempotency key")
    return value


def _repository(row: Any) -> RepositoryRegistration:
    return RepositoryRegistration(str(row[0]), row[1], bool(row[2]), row[3], row[4])


def _allocation(row: Any) -> AllocationBinding:
    return AllocationBinding(str(row[0]), str(row[1]), row[2], row[3], row[4], row[5], row[6], row[7], row[8], row[9])


def get_repository_registration(cur: Any, repository_registration_id: str, *, require_enabled: bool = False) -> RepositoryRegistration:
    repository_registration_id = _repository_id(repository_registration_id)
    cur.execute(
        "SELECT repository_registration_id, canonical_path, enabled, created_at, updated_at "
        "FROM activity.repository_registrations WHERE repository_registration_id=%s",
        (repository_registration_id,),
    )
    row = cur.fetchone()
    if row is None:
        raise RepositoryNotFound("repository registration not found")
    registration = _repository(row)
    if require_enabled and not registration.enabled:
        raise RepositoryDisabled("repository registration is disabled")
    return registration


def resolve_enabled_repository(cur: Any, repository_registration_id: str) -> str:
    return get_repository_registration(cur, repository_registration_id, require_enabled=True).canonical_path


def register_repository(cur: Any, *, repository_registration_id: str, canonical_path: str, enabled: bool = True) -> RepositoryRegistration:
    repository_registration_id = _repository_id(repository_registration_id)
    canonical_path = _canonical_path(canonical_path, "canonical repository path")
    if not isinstance(enabled, bool):
        raise RepositoryPersistenceError("enabled must be boolean")
    cur.execute(
        "SELECT repository_registration_id, canonical_path, enabled, created_at, updated_at "
        "FROM activity.repository_registrations "
        "WHERE repository_registration_id=%s OR canonical_path=%s",
        (repository_registration_id, canonical_path),
    )
    rows = cur.fetchall()
    if rows:
        if len(rows) == 1:
            existing = _repository(rows[0])
            if existing.repository_registration_id == repository_registration_id and existing.canonical_path == canonical_path and existing.enabled == enabled:
                return existing
        raise AllocationConflict("repository identity or canonical path conflicts")
    cur.execute(
        "INSERT INTO activity.repository_registrations "
        "(repository_registration_id, canonical_path, enabled) VALUES (%s,%s,%s)",
        (repository_registration_id, canonical_path, enabled),
    )
    return get_repository_registration(cur, repository_registration_id)


def set_repository_enabled(cur: Any, repository_registration_id: str, enabled: bool) -> RepositoryRegistration:
    repository_registration_id = _repository_id(repository_registration_id)
    if not isinstance(enabled, bool):
        raise RepositoryPersistenceError("enabled must be boolean")
    get_repository_registration(cur, repository_registration_id)
    cur.execute(
        "UPDATE activity.repository_registrations SET enabled=%s, updated_at=now() "
        "WHERE repository_registration_id=%s",
        (enabled, repository_registration_id),
    )
    return get_repository_registration(cur, repository_registration_id)


def get_allocation_by_id(cur: Any, allocation_id: str) -> AllocationBinding | None:
    allocation_id = _canonical_uuid(allocation_id, "allocation identity")
    cur.execute(
        "SELECT allocation_id, task_id, repository_registration_id, worktree_path, task_branch, "
        "baseline_commit, allocation_idempotency_key, state, created_at, updated_at "
        "FROM activity.git_workspaces WHERE allocation_id=%s",
        (allocation_id,),
    )
    row = cur.fetchone()
    return None if row is None else _allocation(row)


def get_allocation_by_idempotency_key(cur: Any, idempotency_key: str) -> AllocationBinding | None:
    idempotency_key = _key(idempotency_key)
    cur.execute(
        "SELECT allocation_id, task_id, repository_registration_id, worktree_path, task_branch, "
        "baseline_commit, allocation_idempotency_key, state, created_at, updated_at "
        "FROM activity.git_workspaces WHERE allocation_idempotency_key=%s",
        (idempotency_key,),
    )
    row = cur.fetchone()
    return None if row is None else _allocation(row)


def insert_allocation_binding(cur: Any, *, allocation_id: str, task_id: str, repository_registration_id: str, worktree_path: str, task_branch: str, baseline_commit: str, idempotency_key: str) -> AllocationBinding:
    allocation_id = _canonical_uuid(allocation_id, "allocation identity")
    task_id = _canonical_uuid(task_id, "task identity")
    repository_registration_id = _repository_id(repository_registration_id)
    worktree_path = _canonical_path(worktree_path, "worktree path")
    task_branch = _branch(task_branch)
    baseline_commit = _commit(baseline_commit)
    idempotency_key = _key(idempotency_key)
    get_repository_registration(cur, repository_registration_id, require_enabled=True)
    expected = (allocation_id, task_id, repository_registration_id, worktree_path, task_branch, baseline_commit, idempotency_key)
    for existing in (get_allocation_by_id(cur, allocation_id), get_allocation_by_idempotency_key(cur, idempotency_key)):
        if existing is not None:
            actual = (existing.allocation_id, existing.task_id, existing.repository_registration_id, existing.worktree_path, existing.task_branch, existing.baseline_commit, existing.idempotency_key)
            if actual == expected:
                return existing
            raise AllocationConflict("conflicting allocation replay")
    cur.execute(
        "SELECT allocation_id, task_id, repository_registration_id, worktree_path, task_branch, baseline_commit, "
        "allocation_idempotency_key, state, created_at, updated_at FROM activity.git_workspaces "
        "WHERE task_id=%s OR worktree_path=%s OR task_branch=%s",
        (task_id, worktree_path, task_branch),
    )
    if cur.fetchone() is not None:
        raise AllocationConflict("allocation identity, task, branch, or path already bound")
    cur.execute(
        "INSERT INTO activity.git_workspaces "
        "(allocation_id, task_id, repository_registration_id, worktree_path, task_branch, baseline_commit, allocation_idempotency_key) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s)",
        expected,
    )
    result = get_allocation_by_id(cur, allocation_id)
    if result is None:
        raise RepositoryPersistenceError("allocation insert was not readable")
    return result


# Explicit aliases keep the internal interface readable at call sites.
get_repository = get_repository_registration
get_allocation = get_allocation_by_id
create_allocation = insert_allocation_binding
