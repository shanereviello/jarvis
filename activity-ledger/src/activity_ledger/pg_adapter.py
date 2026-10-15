from __future__ import annotations

import json
import hashlib
import hmac
import base64
import os
import posixpath
import re
from datetime import datetime, timezone
import stat
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import psycopg

from activity_ledger.execution_state import ExecutionState, ExecutionStateMachine
from activity_ledger.workflow_registry import ContractError, ProfileError, canonical_json, normalized_contract_sha256
from activity_ledger.phase5b_evidence import CustodyResult, RetainedArtifact
from activity_ledger.worktree_allocator import HandoffDescriptor


def secret(name: str) -> str:
    return Path(os.environ[name]).read_text().strip()


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_IDEMPOTENCY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}$")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{43}$")
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
PHASE4B_STAGING_ROOT = Path("/srv/jarvis-activity/runner-state/phase4b-controller-staging")
PHASE4B_RETAINED_ROOT = Path("/srv/jarvis-activity/runner-state/phase4b-controller-retained")
PHASE5A_STAGING_ROOT = Path("/srv/jarvis-activity/runner-state/phase5a-executor-staging")
PHASE5A_RETAINED_ROOT = Path("/srv/jarvis-activity/runner-state/phase5a-executor-retained")
PHASE5A_ARTIFACT_TYPE = "phase5a_model_free_executor_result"
PHASE5A_PROFILE = "phase5a-model-free-executor-v1"
PHASE5A_RECIPE = "phase5a-deterministic-pass-v1"
PHASE5A_SCHEMA = "phase5a-model-free-executor-result"
PHASE5A_EXPECTED_UID = 65532
PHASE5A_EXPECTED_GID = 1000
PHASE5B_PROFILE = "phase5b-codex-executor-v2"
PHASE5B_RESULT_ARTIFACT = "phase5b_codex_executor_result"
PHASE5B_PATCH_ARTIFACT = "phase5b_codex_patch"
PHASE5B_FAILURE_ARTIFACT = "phase5b_codex_failure"
PHASE5B_SUCCESS_ARTIFACT_TYPES = frozenset({PHASE5B_RESULT_ARTIFACT, PHASE5B_PATCH_ARTIFACT})
PHASE5B_ARTIFACT_TYPES = PHASE5B_SUCCESS_ARTIFACT_TYPES | {PHASE5B_FAILURE_ARTIFACT}
PHASE5A_SOURCE_INTERFACE = "phase5a-model-free-executor"
PHASE5B_SOURCE_INTERFACE = "phase5b-codex-executor"
PHASE5B_RETAINED_ROOT = Path("/srv/jarvis-activity/runner-state/phase5b-executor-retained")
_COMMAND_FIELDS = {
    "claim": {"request_id", "contract_sha256", "controller_id", "idempotency_key", "claim_token"},
    "heartbeat": {"request_id", "contract_sha256", "controller_id", "idempotency_key", "claim_id", "claim_token"},
    "running": {"request_id", "contract_sha256", "controller_id", "idempotency_key", "claim_id", "claim_token"},
    "verifying": {"request_id", "contract_sha256", "controller_id", "idempotency_key", "claim_id", "claim_token"},
    "finish": {"request_id", "contract_sha256", "controller_id", "idempotency_key", "claim_id", "claim_token"},
    "fail": {"request_id", "contract_sha256", "controller_id", "idempotency_key", "claim_id", "claim_token", "failure_classification"},
    "recover_expired": {
        "request_id",
        "contract_sha256",
        "actor",
        "idempotency_key",
        "claim_id",
    },
    "evidence": {"request_id", "contract_sha256", "controller_id", "idempotency_key", "claim_id", "claim_token", "artifact_type", "path", "sha256", "size_bytes", "media_type", "metadata"},
}
_PHASE5A_EVIDENCE_FIELDS = frozenset({
    "request_id", "contract_sha256", "controller_id", "idempotency_key", "claim_id",
    "claim_token", "artifact_type", "sha256", "size_bytes", "media_type", "metadata",
})


@dataclass(frozen=True)
class _Phase5APromotion:
    retained_path: str
    retained_receipt: dict[str, int]
    staging_cleanup: Callable[[], bool]


def _uuid(value: object, name: str) -> str:
    if not isinstance(value, str) or str(uuid.UUID(value)) != value:
        raise ValueError(f"invalid {name}")
    return value


def _sha(value: object, name: str = "hash") -> str:
    if not isinstance(value, str) or not _HASH_RE.fullmatch(value):
        raise ValueError(f"invalid {name}")
    return value


def _bounded(value: object, name: str, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum or not _ID_RE.fullmatch(value):
        raise ValueError(f"invalid {name}")
    return value


def _idempotency_key(value: object, name: str = "idempotency_key") -> str:
    if not isinstance(value, str) or not value or len(value) > 256 or not _IDEMPOTENCY_RE.fullmatch(value):
        raise ValueError(f"invalid {name}")
    return value


def _claim_token(value: object) -> str:
    if not isinstance(value, str) or not _TOKEN_RE.fullmatch(value):
        raise ValueError("invalid claim token")
    return value


def _phase4b_descriptor_safety_available() -> bool:
    return all(
        hasattr(os, name) for name in ("O_DIRECTORY", "O_NOFOLLOW", "O_CLOEXEC")
    ) and all(
        operation in os.supports_dir_fd
        for operation in (os.open, os.mkdir, os.unlink, os.link)
    ) and os.link in os.supports_follow_symlinks


def _phase4b_stat_identity(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _phase4b_exact_metadata(controller_id: str, claim_id: str) -> dict[str, str]:
    return {
        "schema_name": "phase4b-fake-controller-result",
        "schema_version": "1",
        "controller_id": controller_id,
        "claim_id": claim_id,
        "outcome": "pass",
    }


def _phase4b_read_validated(
    submitted_path: str,
    request_id: str,
    claim_id: str,
    controller_id: str,
    expected_sha256: str,
    expected_size: int,
) -> bytes:
    request_id = _uuid(request_id, "request_id")
    claim_id = _uuid(claim_id, "claim_id")
    controller_id = _bounded(controller_id, "controller_id", 128)
    expected_sha256 = _sha(expected_sha256, "sha256")
    if isinstance(expected_size, bool) or not isinstance(expected_size, int) or not 0 < expected_size <= 65536:
        raise ValueError("invalid evidence size")
    expected_path = str(PHASE4B_STAGING_ROOT / request_id / f"{claim_id}.json")
    if not isinstance(submitted_path, str) or submitted_path != expected_path or not os.path.isabs(submitted_path):
        raise ValueError("invalid staging evidence path")
    if not _phase4b_descriptor_safety_available():
        raise OSError("required descriptor-safety primitives are unavailable")

    root_fd = request_fd = evidence_fd = None
    try:
        flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
        root_fd = os.open(str(PHASE4B_STAGING_ROOT), flags | os.O_DIRECTORY)
        request_fd = os.open(request_id, flags | os.O_DIRECTORY, dir_fd=root_fd)
        request_info = os.fstat(request_fd)
        if not stat.S_ISDIR(request_info.st_mode):
            raise OSError("staging request component is not a directory")
        evidence_fd = os.open(f"{claim_id}.json", flags, dir_fd=request_fd)
        before = os.fstat(evidence_fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size <= 0 or before.st_size > 65536:
            raise OSError("staging evidence is not a bounded regular file")
        chunks: list[bytes] = []
        total = 0
        while total <= 65536:
            chunk = os.read(evidence_fd, min(8192, 65537 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > 65536:
                raise OSError("staging evidence exceeds maximum size")
        after = os.fstat(evidence_fd)
        if _phase4b_stat_identity(before) != _phase4b_stat_identity(after):
            raise OSError("staging evidence changed while reading")
        content = b"".join(chunks)
    finally:
        for fd in (evidence_fd, request_fd, root_fd):
            if fd is not None:
                os.close(fd)
    if len(content) != expected_size or len(content) != after.st_size:
        raise ValueError("staging evidence size mismatch")
    if hashlib.sha256(content).hexdigest() != expected_sha256:
        raise ValueError("staging evidence digest mismatch")
    try:
        document = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("staging evidence is not UTF-8 JSON") from exc
    if document != _phase4b_exact_metadata(controller_id, claim_id):
        raise ValueError("staging evidence metadata mismatch")
    return content


def promote_phase4b_evidence(
    submitted_path: str,
    request_id: str,
    claim_id: str,
    controller_id: str,
    expected_sha256: str,
    expected_size: int,
) -> dict[str, object]:
    """Validate one staged result and publish it without overwriting retained evidence."""
    content = _phase4b_read_validated(
        submitted_path, request_id, claim_id, controller_id, expected_sha256, expected_size
    )
    retained_path = str(PHASE4B_RETAINED_ROOT / request_id / f"{claim_id}.json")
    if not _phase4b_descriptor_safety_available():
        raise OSError("required descriptor-safety primitives are unavailable")
    root_fd = request_fd = temp_fd = final_fd = None
    request_created = False
    temp_name = f".{claim_id}.{uuid.uuid4().hex}.tmp"
    temp_created = False
    final_created = False
    temp_info = None
    try:
        root_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        root_fd = os.open(str(PHASE4B_RETAINED_ROOT), root_flags)
        try:
            os.mkdir(request_id, 0o750, dir_fd=root_fd)
            request_created = True
            os.fsync(root_fd)
        except FileExistsError:
            pass
        request_fd = os.open(request_id, root_flags, dir_fd=root_fd)
        request_info = os.fstat(request_fd)
        if not stat.S_ISDIR(request_info.st_mode):
            raise OSError("retained request component is not a directory")
        temp_fd = os.open(
            temp_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
            0o640,
            dir_fd=request_fd,
        )
        temp_created = True
        os.fchmod(temp_fd, 0o640)
        written = 0
        while written < len(content):
            count = os.write(temp_fd, content[written:])
            if count <= 0:
                raise OSError("short evidence write")
            written += count
        os.fsync(temp_fd)
        temp_info = os.fstat(temp_fd)
        if not stat.S_ISREG(temp_info.st_mode) or stat.S_IMODE(temp_info.st_mode) != 0o640 or temp_info.st_size != len(content):
            raise OSError("temporary retained evidence verification failed")
        os.link(temp_name, f"{claim_id}.json", src_dir_fd=request_fd, dst_dir_fd=request_fd, follow_symlinks=False)
        final_created = True
        final_fd = os.open(f"{claim_id}.json", os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=request_fd)
        final_info = os.fstat(final_fd)
        if (
            not stat.S_ISREG(final_info.st_mode)
            or (final_info.st_dev, final_info.st_ino) != (temp_info.st_dev, temp_info.st_ino)
            or stat.S_IMODE(final_info.st_mode) != stat.S_IMODE(temp_info.st_mode)
            or final_info.st_size != temp_info.st_size
            or stat.S_IMODE(final_info.st_mode) != 0o640
            or final_info.st_size != len(content)
        ):
            raise OSError("retained evidence verification failed")
        receipt = {"st_dev": final_info.st_dev, "st_ino": final_info.st_ino}
        os.fsync(request_fd)
        os.close(final_fd)
        final_fd = None
        os.close(temp_fd)
        temp_fd = None
        os.unlink(temp_name, dir_fd=request_fd)
        temp_created = False
        os.fsync(request_fd)
    except Exception:
        if temp_fd is not None:
            try:
                os.close(temp_fd)
            except OSError:
                pass
            temp_fd = None
        if final_fd is not None:
            try:
                os.close(final_fd)
            except OSError:
                pass
            final_fd = None
        if request_fd is not None:
            if temp_info is not None:
                try:
                    inspect_fd = os.open(
                        f"{claim_id}.json",
                        os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
                        dir_fd=request_fd,
                    )
                except OSError:
                    inspect_fd = None
                if inspect_fd is not None:
                    try:
                        final_info = os.fstat(inspect_fd)
                        if (
                            stat.S_ISREG(final_info.st_mode)
                            and (final_info.st_dev, final_info.st_ino) == (temp_info.st_dev, temp_info.st_ino)
                        ):
                            os.close(inspect_fd)
                            inspect_fd = None
                            os.unlink(f"{claim_id}.json", dir_fd=request_fd)
                    except OSError:
                        pass
                    finally:
                        if inspect_fd is not None:
                            try:
                                os.close(inspect_fd)
                            except OSError:
                                pass
            if temp_created:
                try:
                    os.unlink(temp_name, dir_fd=request_fd)
                except OSError:
                    pass
            try:
                os.fsync(request_fd)
            except OSError:
                pass
        raise
    finally:
        for fd in (final_fd, request_fd, root_fd):
            if fd is not None:
                os.close(fd)
    return {
        "retained_path": retained_path,
        "sha256": expected_sha256,
        "size_bytes": len(content),
        "metadata": _phase4b_exact_metadata(controller_id, claim_id),
        "cleanup_receipt": receipt,
    }


def cleanup_phase4b_evidence(retained_path: str, cleanup_receipt: dict[str, int]) -> bool:
    """Remove only the exact retained inode identified by a promotion receipt."""
    if not _phase4b_descriptor_safety_available():
        raise OSError("required descriptor-safety primitives are unavailable")
    if not isinstance(cleanup_receipt, dict) or set(cleanup_receipt) != {"st_dev", "st_ino"}:
        raise ValueError("invalid cleanup receipt")
    if any(
        isinstance(cleanup_receipt[name], bool)
        or not isinstance(cleanup_receipt[name], int)
        or cleanup_receipt[name] < 0
        for name in ("st_dev", "st_ino")
    ):
        raise ValueError("invalid cleanup receipt")
    if not isinstance(retained_path, str) or not os.path.isabs(retained_path):
        raise ValueError("invalid retained evidence path")
    try:
        relative = Path(retained_path).relative_to(PHASE4B_RETAINED_ROOT)
    except ValueError as exc:
        raise ValueError("invalid retained evidence path") from exc
    if str(Path(PHASE4B_RETAINED_ROOT) / relative) != retained_path:
        raise ValueError("invalid retained evidence path")
    if len(relative.parts) != 2 or not relative.parts[1].endswith(".json"):
        raise ValueError("invalid retained evidence path")
    _uuid(relative.parts[0], "request_id")
    _uuid(relative.parts[1][:-5], "claim_id")
    root_fd = request_fd = final_fd = None
    try:
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        root_fd = os.open(str(PHASE4B_RETAINED_ROOT), flags)
        request_fd = os.open(relative.parts[0], flags, dir_fd=root_fd)
        final_fd = os.open(relative.parts[1], os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=request_fd)
        info = os.fstat(final_fd)
        if (info.st_dev, info.st_ino) != (cleanup_receipt["st_dev"], cleanup_receipt["st_ino"]):
            return False
        os.close(final_fd)
        final_fd = None
        os.unlink(relative.parts[1], dir_fd=request_fd)
        os.fsync(request_fd)
        return True
    except FileNotFoundError:
        return False
    finally:
        for fd in (final_fd, request_fd, root_fd):
            if fd is not None:
                os.close(fd)


def _phase5a_stat_identity(info: os.stat_result) -> tuple[int, int, int, int, int, int, int, int]:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
            stat.S_IMODE(info.st_mode), info.st_uid, info.st_gid)


def _phase5a_publication_identity(info: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (info.st_dev, info.st_ino, info.st_size, stat.S_IMODE(info.st_mode), info.st_uid, info.st_gid)


def _phase5a_expected_path(root: Path, request_id: str, claim_id: str) -> str:
    return str(root / _uuid(request_id, "request_id") / f"{_uuid(claim_id, 'claim_id')}.json")


def _phase5a_exact_metadata(request_id: str, claim_id: str, run_id: str, contract_sha256: str, work_order_sha256: str) -> dict[str, object]:
    return {
        "schema_name": PHASE5A_SCHEMA, "schema_version": "1",
        "request_id": _uuid(request_id, "request_id"), "claim_id": _uuid(claim_id, "claim_id"),
        "run_id": _uuid(run_id, "run_id"), "contract_sha256": _sha(contract_sha256, "contract_sha256"),
        "executor_profile": PHASE5A_PROFILE, "recipe": PHASE5A_RECIPE, "outcome": "pass",
        "observations": ["deterministic executor completed"],
        "work_order_sha256": _sha(work_order_sha256, "work_order_sha256"),
    }


def _phase5b_expected_retained_path(request_id: str, run_id: str, attempt_number: int, artifact_type: str) -> str:
    request_id, run_id = _uuid(request_id, "request_id"), _uuid(run_id, "run_id")
    if isinstance(attempt_number, bool) or not isinstance(attempt_number, int) or attempt_number != 1:
        raise ValueError("invalid attempt_number")
    if artifact_type not in PHASE5B_ARTIFACT_TYPES:
        raise ValueError("invalid Phase 5B artifact type")
    filename = {PHASE5B_RESULT_ARTIFACT: "result.json", PHASE5B_PATCH_ARTIFACT: "patch.diff", PHASE5B_FAILURE_ARTIFACT: "failure.json"}[artifact_type]
    return str(PHASE5B_RETAINED_ROOT / request_id / run_id / str(attempt_number) / filename)

def _phase5a_validate_file(info: os.stat_result, maximum: int) -> None:
    if (not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= maximum
            or stat.S_IMODE(info.st_mode) != 0o640
            or info.st_uid != PHASE5A_EXPECTED_UID or info.st_gid != PHASE5A_EXPECTED_GID):
        raise OSError("invalid Phase 5A evidence file")


def _phase5a_read_validated(request_id: str, claim_id: str, run_id: str, contract_sha256: str,
                            expected_sha256: str, expected_size: int, metadata: object) -> tuple[bytes, dict[str, int]]:
    request_id, claim_id, run_id = (_uuid(request_id, "request_id"), _uuid(claim_id, "claim_id"), _uuid(run_id, "run_id"))
    contract_sha256, expected_sha256 = _sha(contract_sha256, "contract_sha256"), _sha(expected_sha256, "sha256")
    if isinstance(expected_size, bool) or not isinstance(expected_size, int) or not 0 < expected_size <= 8192:
        raise ValueError("invalid evidence size")
    if not isinstance(metadata, dict) or set(metadata) != {"schema_name", "schema_version", "request_id", "claim_id", "run_id", "contract_sha256", "executor_profile", "recipe", "outcome", "observations", "work_order_sha256"}:
        raise ValueError("invalid Phase 5A evidence metadata")
    expected = _phase5a_exact_metadata(request_id, claim_id, run_id, contract_sha256, metadata.get("work_order_sha256", ""))
    if metadata != expected:
        raise ValueError("Phase 5A evidence metadata mismatch")
    if not _phase4b_descriptor_safety_available():
        raise OSError("required descriptor-safety primitives are unavailable")
    root_fd = request_fd = evidence_fd = None
    try:
        flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
        root_fd = os.open(str(PHASE5A_STAGING_ROOT), flags | os.O_DIRECTORY)
        request_fd = os.open(request_id, flags | os.O_DIRECTORY, dir_fd=root_fd)
        evidence_fd = os.open(f"{claim_id}.json", flags, dir_fd=request_fd)
        before = os.fstat(evidence_fd); _phase5a_validate_file(before, 8192)
        chunks: list[bytes] = []; total = 0
        while total <= 8192:
            chunk = os.read(evidence_fd, min(4096, 8193 - total))
            if not chunk: break
            chunks.append(chunk); total += len(chunk)
            if total > 8192: raise OSError("Phase 5A evidence exceeds maximum size")
        after = os.fstat(evidence_fd)
        if _phase5a_stat_identity(before) != _phase5a_stat_identity(after):
            raise OSError("Phase 5A evidence changed while reading")
        content = b"".join(chunks)
        if len(content) != expected_size or len(content) != after.st_size:
            raise ValueError("Phase 5A evidence size mismatch")
        if hashlib.sha256(content).hexdigest() != expected_sha256:
            raise ValueError("Phase 5A evidence digest mismatch")
        try: document = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc: raise ValueError("Phase 5A evidence is not UTF-8 JSON") from exc
        if document != expected or json.dumps(document, sort_keys=True, separators=(",", ":")).encode() != content:
            raise ValueError("Phase 5A evidence JSON mismatch")
        return content, {"st_dev": before.st_dev, "st_ino": before.st_ino}
    finally:
        for fd in (evidence_fd, request_fd, root_fd):
            if fd is not None: os.close(fd)


def promote_phase5a_evidence(request_id: str, claim_id: str, run_id: str, contract_sha256: str,
                             expected_sha256: str, expected_size: int, metadata: object) -> dict[str, object]:
    content, staging_receipt = _phase5a_read_validated(request_id, claim_id, run_id, contract_sha256, expected_sha256, expected_size, metadata)
    request_id, claim_id = _uuid(request_id, "request_id"), _uuid(claim_id, "claim_id")
    retained_path = _phase5a_expected_path(PHASE5A_RETAINED_ROOT, request_id, claim_id)
    root_fd = request_fd = temp_fd = final_fd = None
    temp_name = f".{claim_id}.{uuid.uuid4().hex}.tmp"; temp_created = final_created = False; temp_info = None
    try:
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        root_fd = os.open(str(PHASE5A_RETAINED_ROOT), flags)
        try: os.mkdir(request_id, 0o2750, dir_fd=root_fd); os.fsync(root_fd)
        except FileExistsError: pass
        request_fd = os.open(request_id, flags, dir_fd=root_fd)
        temp_fd = os.open(temp_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW, 0o640, dir_fd=request_fd)
        temp_created = True; os.fchmod(temp_fd, 0o640)
        written = 0
        while written < len(content):
            count = os.write(temp_fd, content[written:])
            if count <= 0: raise OSError("short Phase 5A evidence write")
            written += count
        os.fsync(temp_fd); temp_info = os.fstat(temp_fd); _phase5a_validate_file(temp_info, 8192)
        os.link(temp_name, f"{claim_id}.json", src_dir_fd=request_fd, dst_dir_fd=request_fd, follow_symlinks=False); final_created = True
        final_fd = os.open(f"{claim_id}.json", os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=request_fd)
        final_info = os.fstat(final_fd)
        if _phase5a_publication_identity(final_info) != _phase5a_publication_identity(temp_info): raise OSError("Phase 5A retained identity mismatch")
        os.fsync(request_fd); os.close(final_fd); final_fd = None; os.close(temp_fd); temp_fd = None
        os.unlink(temp_name, dir_fd=request_fd); temp_created = False; os.fsync(request_fd)
        retained_receipt = {"st_dev": final_info.st_dev, "st_ino": final_info.st_ino}
    except Exception:
        for fd in (final_fd, temp_fd):
            if fd is not None:
                try: os.close(fd)
                except OSError: pass
        final_fd = None
        temp_fd = None
        if request_fd is not None:
            if temp_created:
                try: os.unlink(temp_name, dir_fd=request_fd)
                except OSError: pass
            if final_created and temp_info is not None:
                try:
                    check_fd = os.open(f"{claim_id}.json", os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=request_fd)
                    check = os.fstat(check_fd); os.close(check_fd)
                    if (check.st_dev, check.st_ino) == (temp_info.st_dev, temp_info.st_ino): os.unlink(f"{claim_id}.json", dir_fd=request_fd)
                except OSError: pass
            try: os.fsync(request_fd)
            except OSError: pass
        raise
    finally:
        for fd in (final_fd, temp_fd, request_fd, root_fd):
            if fd is not None: os.close(fd)
    return {"retained_path": retained_path, "sha256": expected_sha256, "size_bytes": len(content),
            "media_type": "application/json", "artifact_type": PHASE5A_ARTIFACT_TYPE,
            "metadata": metadata, "cleanup_receipt": retained_receipt, "staging_receipt": staging_receipt}


def cleanup_phase5a_staging(request_id: str, claim_id: str, receipt: dict[str, int]) -> bool:
    request_id, claim_id = _uuid(request_id, "request_id"), _uuid(claim_id, "claim_id")
    if not isinstance(receipt, dict) or set(receipt) != {"st_dev", "st_ino"} or any(isinstance(receipt[k], bool) or not isinstance(receipt[k], int) or receipt[k] < 0 for k in receipt):
        raise ValueError("invalid staging cleanup receipt")
    root_fd = request_fd = evidence_fd = None
    try:
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        root_fd = os.open(str(PHASE5A_STAGING_ROOT), flags); request_fd = os.open(request_id, flags, dir_fd=root_fd)
        evidence_fd = os.open(f"{claim_id}.json", os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=request_fd)
        info = os.fstat(evidence_fd)
        if (info.st_dev, info.st_ino) != (receipt["st_dev"], receipt["st_ino"]): return False
        os.close(evidence_fd); evidence_fd = None; os.unlink(f"{claim_id}.json", dir_fd=request_fd); os.fsync(request_fd)
        os.rmdir(request_id, dir_fd=root_fd)
        os.fsync(root_fd)
        return True
    except FileNotFoundError: return False
    finally:
        for fd in (evidence_fd, request_fd, root_fd):
            if fd is not None: os.close(fd)


def reconcile_phase5a_staging_absence(request_id: str) -> bool:
    request_id = _uuid(request_id, "request_id")
    root_fd = request_fd = None
    try:
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        root_fd = os.open(str(PHASE5A_STAGING_ROOT), flags)
        try:
            request_fd = os.open(request_id, flags, dir_fd=root_fd)
        except FileNotFoundError:
            return True
        if os.listdir(request_fd):
            return False
        os.close(request_fd); request_fd = None
        os.rmdir(request_id, dir_fd=root_fd)
        os.fsync(root_fd)
        return True
    except FileNotFoundError:
        return True
    except OSError:
        return False
    finally:
        for fd in (request_fd, root_fd):
            if fd is not None: os.close(fd)


def connect():
    return psycopg.connect(
        host=os.environ["JARVIS_ACTIVITY_DB_HOST"],
        dbname=os.environ["JARVIS_ACTIVITY_DB_NAME"],
        user=os.environ["JARVIS_ACTIVITY_DB_USER"],
        password=Path(os.environ["JARVIS_ACTIVITY_DB_PASSWORD_FILE"]).read_text().strip(),
    )


def _commit_then_respond(db, status: int, body: dict, send) -> None:
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    send(status, body)


def _run_controller_transaction(db, write, send, cleanup=cleanup_phase4b_evidence) -> None:
    """Run a controller write with promotion cleanup strictly before commit only."""
    promotions: list[tuple[str, dict]] = []
    committed = False
    try:
        status, result = write(promotions)
        db.commit()
        committed = True
    except Exception:
        if not committed:
            try:
                db.rollback()
            except Exception:
                pass
            for promotion in reversed(promotions):
                if isinstance(promotion, _Phase5APromotion):
                    retained_path, receipt = promotion.retained_path, promotion.retained_receipt
                else:
                    retained_path, receipt = promotion
                try:
                    cleanup(retained_path, receipt)
                except Exception:
                    pass
            try:
                send(500, {"error": "internal server error"})
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
        return
    post_commit = [promotion.staging_cleanup for promotion in promotions if isinstance(promotion, _Phase5APromotion)]
    promotions.clear()
    for cleanup_staging in post_commit:
        try:
            if not cleanup_staging():
                send(500, {"error": "evidence cleanup could not be proven"})
                return
        except Exception:
            try:
                send(500, {"error": "evidence cleanup could not be proven"})
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            return
    try:
        send(status, result)
    except Exception:
        pass


def _state(value: str) -> ExecutionState:
    return ExecutionState(value)


def _next_sequence(cur, request_id: str) -> int:
    cur.execute(
        "SELECT COALESCE(MAX(sequence_number), 0) + 1 "
        "FROM activity.execution_request_events "
        "WHERE execution_request_id=%s",
        (request_id,),
    )
    return int(cur.fetchone()[0])


def _record_event(cur, request_id: str, sequence: int, event_key: str, event_type: str, from_state: str | None, to_state: str, actor: str, metadata: dict) -> None:
    cur.execute(
        "INSERT INTO activity.execution_request_events "
        "(id, execution_request_id, sequence_number, idempotency_key, event_type, from_state, to_state, actor, metadata) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (uuid.uuid4(), request_id, sequence, event_key, event_type, from_state, to_state, actor, json.dumps(metadata)),
    )


def _transition(cur, request_id: str, current: str, target: ExecutionState, actor: str, event_key: str, metadata: dict) -> None:
    machine = ExecutionStateMachine(_state(current))
    machine.transition(target)
    sequence = _next_sequence(cur, request_id)
    _record_event(cur, request_id, sequence, event_key, "state_transition", current, target.value, actor, metadata)
    cur.execute("UPDATE activity.execution_requests SET current_state=%s WHERE id=%s", (target.value, request_id))


class Handler(BaseHTTPRequestHandler):
    def _json(self, status: int, body: dict) -> None:
        encoded = json.dumps(body, sort_keys=True).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _authorized(self, role: str = "operator") -> bool:
        env_name = "JARVIS_CONTROLLER_TOKEN_FILE" if role == "controller" else "JARVIS_ADAPTER_TOKEN_FILE"
        supplied = self.headers.get("Authorization", "")
        try:
            expected = f"Bearer {secret(env_name)}"
        except (KeyError, OSError, ValueError):
            self._json(401, {"error": "unauthorized"})
            return False
        if hmac.compare_digest(supplied, expected):
            return True
        self._json(401, {"error": "unauthorized"})
        return False

    def do_GET(self) -> None:
        if urlparse(self.path).path == "/healthz":
            try:
                with connect() as db, db.cursor() as cur:
                    cur.execute("SELECT 1")
                self._json(200, {"status": "ok"})
            except Exception:
                self._json(503, {"status": "unavailable"})
            return
        if not self._authorized():
            return
        path = urlparse(self.path).path
        try:
            with connect() as db, db.cursor() as cur:
                if path.startswith("/v1/execution-requests/"):
                    request_id = path.removeprefix("/v1/execution-requests/")
                    request_id = _uuid(request_id, "request_id")
                    cur.execute(
                        "SELECT id, idempotency_key, operation, workflow_template, executor_profile, "
                        "contract_sha256, current_state, requested_by, created_at, validated_at, "
                        "started_at, finished_at FROM activity.execution_requests WHERE id=%s",
                        (request_id,),
                    )
                    request = cur.fetchone()
                    if request is None:
                        self._json(404, {"error": "execution request not found"})
                        return
                    cur.execute(
                        "SELECT execution_request_id, associated_run_count, associated_run_id, run_status, "
                        "run_finished_at, run_actor, run_source_interface, controller_lease_count, "
                        "active_controller_lease_count, latest_controller_lease_state, latest_controller_id, "
                        "latest_controller_attempt_number, latest_controller_released_at, writer_lease_count, "
                        "active_writer_lease_count FROM activity.get_execution_request_runtime_summary(%s)",
                        (request_id,),
                    )
                    runtime = cur.fetchone()
                    if runtime is None:
                        raise RuntimeError("execution request runtime summary unavailable")
                    runtime_summary = {
                        "execution_request_id": str(runtime[0]),
                        "associated_run_count": runtime[1],
                        "associated_run_id": str(runtime[2]) if runtime[2] else None,
                        "run_status": runtime[3],
                        "run_finished_at": runtime[4].isoformat() if runtime[4] else None,
                        "run_actor": runtime[5],
                        "run_source_interface": runtime[6],
                        "controller_lease_count": runtime[7],
                        "active_controller_lease_count": runtime[8],
                        "latest_controller_lease_state": runtime[9],
                        "latest_controller_id": runtime[10],
                        "latest_controller_attempt_number": runtime[11],
                        "latest_controller_released_at": runtime[12].isoformat() if runtime[12] else None,
                        "writer_lease_count": runtime[13],
                        "active_writer_lease_count": runtime[14],
                    }
                    cur.execute(
                        "SELECT sequence_number, idempotency_key, event_type, from_state, to_state, actor, metadata, created_at "
                        "FROM activity.execution_request_events WHERE execution_request_id=%s ORDER BY sequence_number",
                        (request_id,),
                    )
                    events = [
                        {"sequence_number": r[0], "idempotency_key": r[1], "event_type": r[2], "from_state": r[3], "to_state": r[4], "actor": r[5], "metadata": r[6], "created_at": r[7].isoformat()}
                        for r in cur.fetchall()
                    ]
                    cur.execute(
                        "SELECT approval_gate, actor, decision, contract_sha256, idempotency_key, created_at "
                        "FROM activity.execution_approvals WHERE execution_request_id=%s ORDER BY created_at",
                        (request_id,),
                    )
                    approvals = [{"approval_gate": r[0], "actor": r[1], "decision": r[2], "contract_sha256": r[3], "idempotency_key": r[4], "created_at": r[5].isoformat()} for r in cur.fetchall()]
                    cur.execute(
                        "SELECT run_id, artifact_type, protected_absolute_path, sha256, size_bytes, media_type, created_at, metadata "
                        "FROM activity.run_artifacts WHERE execution_request_id=%s ORDER BY created_at",
                        (request_id,),
                    )
                    artifacts = [{"run_id": str(r[0]) if r[0] else None, "artifact_type": r[1], "protected_absolute_path": r[2], "sha256": r[3], "size_bytes": r[4], "media_type": r[5], "created_at": r[6].isoformat(), "metadata": r[7]} for r in cur.fetchall()]
                    self._json(200, {"request_id": str(request[0]), "idempotency_key": request[1], "operation": request[2], "workflow_template": request[3], "executor_profile": request[4], "contract_sha256": request[5], "state": request[6], "requested_by": request[7], "created_at": request[8].isoformat(), "validated_at": request[9].isoformat() if request[9] else None, "started_at": request[10].isoformat() if request[10] else None, "finished_at": request[11].isoformat() if request[11] else None, "runtime_summary": runtime_summary, "events": events, "approvals": approvals, "artifacts": artifacts})
                    return
                if path.startswith("/v1/tasks/") and "/runs" not in path:
                    task_key = path.removeprefix("/v1/tasks/")
                    cur.execute("SELECT id, task_key, title, description, origin_type, state, created_at, updated_at, run_count, active_writer_lease_count FROM activity.get_task_summary(%s)", (task_key,))
                    row = cur.fetchone()
                    result = {"id": str(row[0]), "task_key": row[1], "title": row[2], "description": row[3], "origin_type": row[4], "state": row[5], "created_at": row[6].isoformat(), "updated_at": row[7].isoformat(), "run_count": row[8], "active_writer_lease_count": row[9]} if row else {"error": "task not found"}
                    self._json(200, result)
                    return
                if path.startswith("/v1/runs/") and path.endswith("/events"):
                    run_id = path.removeprefix("/v1/runs/").removesuffix("/events")
                    cur.execute("SELECT sequence_number, idempotency_key, event_type, payload, created_at FROM activity.events WHERE run_id=%s ORDER BY sequence_number", (run_id,))
                    self._json(200, {"events": [{"sequence_number": r[0], "idempotency_key": r[1], "event_type": r[2], "payload": r[3], "created_at": r[4].isoformat()} for r in cur.fetchall()]})
                    return
                if path.startswith("/v1/runs/"):
                    run_id = path.removeprefix("/v1/runs/")
                    cur.execute("SELECT id, task_id, actor, source_interface, status, started_at, finished_at FROM activity.runs WHERE id=%s", (run_id,))
                    row = cur.fetchone()
                    self._json(200, {"run_id": str(row[0]), "task_id": str(row[1]), "actor": row[2], "source_interface": row[3], "status": row[4], "started_at": row[5].isoformat(), "finished_at": row[6].isoformat() if row[6] else None} if row else {"error": "run not found"})
                    return
        except Exception as exc:
            self._json(400, {"error": type(exc).__name__})
            return
        self._json(404, {"error": "not found"})

    def _controller_request_document(self, command: str, body: dict, claim_hash: str | None = None) -> dict:
        allowed = _COMMAND_FIELDS.get(command)
        if allowed is None or set(body) - allowed:
            raise ValueError("unknown controller command field")
        document = {key: body[key] for key in sorted(body) if key not in {"claim_token"}}
        document["command_type"] = command
        if claim_hash is not None and command != "recover_expired":
            document["claim_token_sha256"] = claim_hash
        return document

    def _controller_request_hash(self, command: str, body: dict, claim_hash: str | None = None) -> str:
        document = self._controller_request_document(command, body, claim_hash)
        return hashlib.sha256(json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def _controller_command(self, cur, request_id: str, command: str, key: str, actor: str, controller_id: str, request_hash: str):
        cur.execute("SELECT actor, controller_id, command_type, request_sha256, response_metadata FROM activity.execution_controller_commands WHERE execution_request_id=%s AND idempotency_key=%s", (request_id, key))
        prior = cur.fetchone()
        if prior is None:
            return None
        if prior[0] == actor and prior[1] == controller_id and prior[2] == command and prior[3] == request_hash:
            if prior[4] is not None and not isinstance(prior[4], dict):
                return 409, {"error": "stored controller response is invalid"}
            response = dict(prior[4] or {})
            response["duplicate"] = True
            return 200, response
        return 409, {"error": "controller command idempotency key conflict"}

    def _record_controller_command(self, cur, request_id: str, lease_id: str | None, command: str, key: str, actor: str, controller_id: str, request_hash: str, response: dict) -> None:
        safe = {name: response[name] for name in ("request_id", "claim_id", "attempt_number", "run_id", "state", "artifact_id", "duplicate", "lease_expires_at") if name in response}
        cur.execute("INSERT INTO activity.execution_controller_commands (id, execution_request_id, controller_lease_id, actor, controller_id, command_type, idempotency_key, request_sha256, response_metadata) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)", (uuid.uuid4(), request_id, lease_id, actor, controller_id, command, key, request_hash, json.dumps(safe)))

    def _phase5b_bind_execution(self, cur, request_id: str, claim_id: str, run_id: str, allocation_id: str, work_order: dict) -> tuple[int, dict]:
        """Persist one immutable request/claim/run/allocation/work-order binding."""
        try:
            request_id, claim_id, run_id, allocation_id = (_uuid(value, name) for value, name in ((request_id, "request_id"), (claim_id, "claim_id"), (run_id, "run_id"), (allocation_id, "allocation_id")))
            if not isinstance(work_order, dict) or not work_order:
                raise ValueError("invalid work order")
            encoded = json.dumps(work_order, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
            digest = hashlib.sha256(encoded.encode()).hexdigest()
        except (TypeError, ValueError) as exc:
            return 400, {"error": str(exc)}
        cur.execute("SELECT 1 FROM activity.execution_controller_leases WHERE id=%s AND execution_request_id=%s AND state='active' AND lease_expires_at > now()", (claim_id, request_id))
        if cur.fetchone() is None:
            return 409, {"error": "active controller lease is required"}
        cur.execute("SELECT 1 FROM activity.runs WHERE id=%s AND execution_request_id=%s", (run_id, request_id))
        if cur.fetchone() is None:
            return 409, {"error": "run binding is required"}
        cur.execute("SELECT 1 FROM activity.git_workspaces WHERE allocation_id=%s", (allocation_id,))
        if cur.fetchone() is None:
            return 409, {"error": "allocation binding is required"}
        cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (request_id,))
        cur.execute("SELECT controller_lease_id, run_id, allocation_id, work_order_sha256, work_order FROM activity.phase5b_execution_bindings WHERE execution_request_id=%s", (request_id,))
        prior = cur.fetchone()
        if prior is not None:
            same = (str(prior[0]) == claim_id and str(prior[1]) == run_id and str(prior[2]) == allocation_id and prior[3] == digest and prior[4] == work_order)
            return (200, {"request_id": request_id, "claim_id": claim_id, "run_id": run_id, "allocation_id": allocation_id, "work_order_sha256": digest, "duplicate": True}) if same else (409, {"error": "Phase 5B execution binding conflict"})
        cur.execute("INSERT INTO activity.phase5b_execution_bindings (execution_request_id, controller_lease_id, run_id, allocation_id, work_order_sha256, work_order) VALUES (%s,%s,%s,%s,%s,%s)", (request_id, claim_id, run_id, allocation_id, digest, json.dumps(work_order, ensure_ascii=False, sort_keys=True, separators=(",", ":"))))
        return 200, {"request_id": request_id, "claim_id": claim_id, "run_id": run_id, "allocation_id": allocation_id, "work_order_sha256": digest, "duplicate": False}

    def _phase5b_read_execution(self, cur, request_id: str) -> tuple[int, dict]:
        request_id = _uuid(request_id, "request_id")
        cur.execute("SELECT controller_lease_id, run_id, allocation_id, work_order_sha256, work_order FROM activity.phase5b_execution_bindings WHERE execution_request_id=%s", (request_id,))
        row = cur.fetchone()
        if row is None:
            return 404, {"error": "Phase 5B execution binding not found"}
        if not isinstance(row[4], dict) or hashlib.sha256(json.dumps(row[4], ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest() != row[3]:
            return 409, {"error": "stored Phase 5B work order is corrupt"}
        return 200, {"request_id": request_id, "claim_id": str(row[0]), "run_id": str(row[1]), "allocation_id": str(row[2]), "work_order_sha256": row[3], "work_order": row[4], "duplicate": False}

    def _phase5b_register_artifact(self, cur, request_id: str, run_id: str, attempt_number: int, idempotency_key: str, artifact: dict) -> tuple[int, dict]:
        required = {"artifact_id", "artifact_type", "retained_path", "sha256", "size_bytes", "media_type", "metadata"}
        if set(artifact) != required or artifact["artifact_type"] not in PHASE5B_ARTIFACT_TYPES:
            return 400, {"error": "invalid Phase 5B artifact descriptor"}
        try:
            request_id, run_id = _uuid(request_id, "request_id"), _uuid(run_id, "run_id")
            _idempotency_key(idempotency_key); _sha(artifact["sha256"], "sha256")
            expected_path = _phase5b_expected_retained_path(request_id, run_id, attempt_number, artifact["artifact_type"])
            if artifact["retained_path"] != expected_path or isinstance(artifact["size_bytes"], bool) or not isinstance(artifact["size_bytes"], int) or not 0 < artifact["size_bytes"] <= 131072 or not isinstance(artifact["metadata"], dict):
                raise ValueError("invalid retained Phase 5B artifact binding")
        except (TypeError, ValueError) as exc:
            return 400, {"error": str(exc)}
        cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (request_id,))
        cur.execute("SELECT allocation_id FROM activity.phase5b_execution_bindings WHERE execution_request_id=%s AND run_id=%s", (request_id, run_id))
        binding = cur.fetchone()
        if binding is None:
            return 409, {"error": "Phase 5B execution binding is required"}
        cur.execute("SELECT id, run_id, idempotency_key, protected_absolute_path, sha256, size_bytes, media_type, metadata FROM activity.run_artifacts WHERE execution_request_id=%s AND artifact_type=%s", (request_id, artifact["artifact_type"]))
        prior = cur.fetchone()
        comparable = (str(prior[0]), str(prior[1]), prior[2], prior[3], prior[4], prior[5], prior[6], prior[7]) if prior else None
        candidate = (artifact["artifact_id"], run_id, idempotency_key, artifact["retained_path"], artifact["sha256"], artifact["size_bytes"], artifact["media_type"], artifact["metadata"])
        if prior is not None:
            return (200, {"artifact_id": str(prior[0]), "artifact_type": artifact["artifact_type"], "duplicate": True}) if comparable == candidate else (409, {"error": "Phase 5B artifact registration conflict"})
        cur.execute("INSERT INTO activity.run_artifacts (id, execution_request_id, run_id, idempotency_key, artifact_type, protected_absolute_path, sha256, size_bytes, media_type, metadata) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (artifact["artifact_id"], request_id, run_id, idempotency_key, artifact["artifact_type"], artifact["retained_path"], artifact["sha256"], artifact["size_bytes"], artifact["media_type"], json.dumps(artifact["metadata"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))))
        return 200, {"artifact_id": artifact["artifact_id"], "artifact_type": artifact["artifact_type"], "duplicate": False}

    def _phase5b_finish(self, cur, request_id: str, body: dict, request_hash: str) -> tuple[int, dict]:
        request_id = _uuid(request_id, "request_id")
        cur.execute("SELECT contract_sha256, current_state, executor_profile FROM activity.execution_requests WHERE id=%s FOR UPDATE", (request_id,))
        request = cur.fetchone()
        key = body["idempotency_key"]
        prior = self._controller_command(cur, request_id, "finish", key, body["controller_id"], body["controller_id"], request_hash)
        if prior is not None:
            return prior
        if request is None or request[2] != PHASE5B_PROFILE or request[1] != ExecutionState.VERIFYING.value:
            return 409, {"error": "Phase 5B finish requires verifying request"}
        if self._phase5b_cancellation(cur, request_id):
            return 409, {"error": "cancellation pending; preserve exclusion"}
        lease, _ = self._active_controller_lease(cur, request_id, request[0], body)
        if lease is None:
            return 409, {"error": "claim is expired, released, or mismatched"}
        cur.execute("SELECT id FROM activity.runs WHERE execution_request_id=%s", (request_id,))
        run = cur.fetchone()
        cur.execute("SELECT artifact_type FROM activity.run_artifacts WHERE execution_request_id=%s AND run_id=%s AND artifact_type IN (%s,%s)", (request_id, run[0] if run else None, PHASE5B_RESULT_ARTIFACT, PHASE5B_PATCH_ARTIFACT))
        artifacts = {row[0] for row in cur.fetchall()}
        if run is None or artifacts != set(PHASE5B_SUCCESS_ARTIFACT_TYPES):
            return 409, {"error": "both retained Phase 5B artifacts are required"}
        cur.execute("UPDATE activity.runs SET status='awaiting_review', finished_at=now() WHERE id=%s", (run[0],))
        _transition(cur, request_id, request[1], ExecutionState.AWAITING_REVIEW, body["controller_id"], f"controller:{lease[0]}:awaiting_review", {})
        cur.execute("UPDATE activity.execution_controller_leases SET state='released', released_at=now() WHERE id=%s AND state='active'", (lease[0],))
        response = {"claim_id": str(lease[0]), "run_id": str(run[0]), "state": ExecutionState.AWAITING_REVIEW.value, "duplicate": False}
        self._record_controller_command(cur, request_id, str(lease[0]), "finish", key, body["controller_id"], body["controller_id"], request_hash, response)
        return 200, response

    def _phase5b_writer_acquire(self, cur, request_id: str, claim_id: str, run_id: str, allocation_id: str, worktree_id: str, owner_id: str, generation: int, fence_sha256: str, ttl_seconds: int) -> tuple[int, dict]:
        for value, name in ((request_id, "request_id"), (claim_id, "claim_id"), (run_id, "run_id"), (allocation_id, "allocation_id"), (worktree_id, "worktree_id")):
            _uuid(value, name)
        _sha(fence_sha256, "fence_sha256")
        if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1 or not 5 <= ttl_seconds <= 300:
            return 400, {"error": "invalid writer lease bounds"}
        cur.execute("SELECT 1 FROM activity.execution_controller_leases WHERE id=%s AND execution_request_id=%s AND state='active' AND lease_expires_at > now()", (claim_id, request_id))
        if cur.fetchone() is None:
            return 409, {"error": "active controller lease is required"}
        cur.execute("SELECT 1 FROM activity.runs WHERE id=%s AND execution_request_id=%s", (run_id, request_id))
        if cur.fetchone() is None:
            return 409, {"error": "run binding is required"}
        cur.execute("SELECT 1 FROM activity.git_workspaces WHERE allocation_id=%s", (allocation_id,))
        if cur.fetchone() is None:
            return 409, {"error": "allocation binding is required"}
        cur.execute("SELECT id FROM activity.phase5b_execution_writer_leases WHERE allocation_id=%s AND state='active' FOR UPDATE", (allocation_id,))
        if cur.fetchone() is not None:
            return 409, {"error": "active Phase 5B writer already exists"}
        writer_id = str(uuid.uuid4())
        cur.execute("INSERT INTO activity.phase5b_execution_writer_leases (id, execution_request_id, controller_lease_id, run_id, allocation_id, worktree_id, writer_id, owner_id, generation, fence_sha256, state, lease_expires_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'active',now() + (%s * interval '1 second')) RETURNING lease_expires_at", (uuid.uuid4(), request_id, claim_id, run_id, allocation_id, worktree_id, writer_id, owner_id, generation, fence_sha256, ttl_seconds))
        expiry = cur.fetchone()[0]
        return 200, {"allocation_id": allocation_id, "writer_id": writer_id, "generation": generation, "fence_sha256": fence_sha256, "lease_expires_at": self._lease_expiry(expiry), "duplicate": False}

    def _phase5b_writer_renew(self, cur, allocation_id: str, writer_id: str, generation: int, fence_sha256: str, ttl_seconds: int) -> tuple[int, dict]:
        _uuid(allocation_id, "allocation_id"); _sha(fence_sha256, "fence_sha256")
        if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1 or not 5 <= ttl_seconds <= 300:
            return 400, {"error": "invalid writer renewal bounds"}
        cur.execute("UPDATE activity.phase5b_execution_writer_leases SET lease_expires_at=now() + (%s * interval '1 second') WHERE allocation_id=%s AND writer_id=%s AND generation=%s AND fence_sha256=%s AND state='active' AND lease_expires_at > now() RETURNING lease_expires_at", (ttl_seconds, allocation_id, writer_id, generation, fence_sha256))
        row = cur.fetchone()
        return (200, {"allocation_id": allocation_id, "generation": generation, "lease_expires_at": self._lease_expiry(row[0]), "duplicate": False}) if row else (409, {"error": "writer fence is stale or expired"})

    def _phase5b_writer_release(self, cur, allocation_id: str, writer_id: str, generation: int, fence_sha256: str) -> tuple[int, dict]:
        _uuid(allocation_id, "allocation_id"); _sha(fence_sha256, "fence_sha256")
        cur.execute("UPDATE activity.phase5b_execution_writer_leases SET state='released', released_at=now() WHERE allocation_id=%s AND writer_id=%s AND generation=%s AND fence_sha256=%s AND state='active' RETURNING id", (allocation_id, writer_id, generation, fence_sha256))
        return (200, {"allocation_id": allocation_id, "generation": generation, "duplicate": False}) if cur.fetchone() else (409, {"error": "writer fence is stale or already released"})

    @staticmethod
    def _lease_expiry(value) -> str:
        if value is None or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("invalid lease expiry")
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    def _ttl(self) -> int:
        try:
            ttl = int(os.environ.get("JARVIS_CONTROLLER_LEASE_TTL_SECONDS", "30"))
        except ValueError as exc:
            raise ValueError("invalid controller lease TTL") from exc
        if not 5 <= ttl <= 300:
            raise ValueError("controller lease TTL outside safe bounds")
        return ttl

    def _active_controller_lease(self, cur, request_id: str, contract_hash: str, body: dict):
        claim_id = body.get("claim_id")
        controller_id = body.get("controller_id")
        claim_token = body.get("claim_token")
        if not (claim_id and controller_id and claim_token):
            raise ValueError("claim_id, controller_id, and claim_token are required")
        claim_hash = token_hash(claim_token)
        cur.execute("SELECT id, state, controller_id, claim_token_sha256, lease_expires_at, lease_expires_at <= now() FROM activity.execution_controller_leases WHERE id=%s AND execution_request_id=%s FOR UPDATE", (claim_id, request_id))
        lease = cur.fetchone()
        if lease is None or lease[2] != controller_id or lease[3] != claim_hash or lease[1] != "active" or lease[5]:
            return None, claim_hash
        return lease, claim_hash

    def _phase5a_retained_valid(self, retained_path: str, request_id: str, claim_id: str,
                                expected_sha256: str, expected_size: int, metadata: object) -> bool:
        if retained_path != _phase5a_expected_path(PHASE5A_RETAINED_ROOT, request_id, claim_id):
            return False
        root_fd = request_fd = evidence_fd = None
        try:
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
            root_fd = os.open(str(PHASE5A_RETAINED_ROOT), flags)
            request_fd = os.open(_uuid(request_id, "request_id"), flags, dir_fd=root_fd)
            evidence_fd = os.open(f"{_uuid(claim_id, 'claim_id')}.json", os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=request_fd)
            before = os.fstat(evidence_fd); _phase5a_validate_file(before, 8192)
            if before.st_size != expected_size: return False
            chunks: list[bytes] = []
            while sum(map(len, chunks)) <= expected_size:
                chunk = os.read(evidence_fd, min(4096, expected_size + 1 - sum(map(len, chunks))))
                if not chunk:
                    break
                chunks.append(chunk)
            content = b"".join(chunks)
            after = os.fstat(evidence_fd)
            if (_phase5a_stat_identity(before) != _phase5a_stat_identity(after)
                    or len(content) != expected_size
                    or hashlib.sha256(content).hexdigest() != expected_sha256):
                return False
            document = json.loads(content.decode("utf-8"))
            return document == metadata and json.dumps(document, sort_keys=True, separators=(",", ":")).encode() == content
        except (OSError, ValueError):
            return False
        finally:
            for fd in (evidence_fd, request_fd, root_fd):
                if fd is not None: os.close(fd)

    def _phase5a_evidence(self, cur, request_id: str, contract_hash: str, controller_id: str,
                          key: str, body: dict, lease_id: str, request_state: str,
                          request_hash: str, promotions: list[object]) -> tuple[int, dict]:
        if set(body) != _PHASE5A_EVIDENCE_FIELDS:
            return 400, {"error": "invalid Phase 5A evidence fields"}
        if (request_state not in {ExecutionState.RUNNING.value, ExecutionState.VERIFYING.value}
                or body.get("artifact_type") != PHASE5A_ARTIFACT_TYPE
                or body.get("media_type") != "application/json"
                or not isinstance(body.get("metadata"), dict)):
            return 400, {"error": "invalid Phase 5A evidence"}
        cur.execute("SELECT id, source_interface FROM activity.runs WHERE execution_request_id=%s", (request_id,))
        run = cur.fetchone()
        if run is None or len(run) < 2 or run[1] != "phase5a-model-free-executor":
            return 409, {"error": "associated Phase 5A run is required"}
        run_id = str(run[0])
        prior = self._controller_command(cur, request_id, "evidence", key, controller_id, controller_id, request_hash)
        if prior is not None:
            if prior[0] != 200: return prior
            if not {"claim_id", "artifact_id"}.issubset(prior[1]):
                return 409, {"error": "stored Phase 5A response is incomplete"}
            cur.execute("SELECT run_id, idempotency_key, protected_absolute_path, sha256, size_bytes, media_type, metadata FROM activity.run_artifacts WHERE execution_request_id=%s AND artifact_type=%s", (request_id, PHASE5A_ARTIFACT_TYPE))
            artifact = cur.fetchone()
            if (artifact is None or artifact[0] != run_id or artifact[1] != key
                    or artifact[5] != "application/json" or artifact[3] != body.get("sha256")
                    or artifact[4] != body.get("size_bytes") or artifact[6] != body["metadata"]):
                return 409, {"error": "committed Phase 5A artifact identity mismatch"}
            try:
                staging_metadata = artifact[6]
                _, receipt = _phase5a_read_validated(request_id, lease_id, run_id, contract_hash, artifact[3], artifact[4], staging_metadata)
                cleanup_staging = lambda: cleanup_phase5a_staging(request_id, lease_id, receipt)
                if not cleanup_staging(): return 500, {"error": "evidence cleanup could not be proven"}
            except FileNotFoundError:
                if not reconcile_phase5a_staging_absence(request_id):
                    return 500, {"error": "evidence cleanup could not be proven"}
            except (OSError, ValueError):
                return 409, {"error": "staging evidence identity mismatch"}
            if not self._phase5a_retained_valid(artifact[2], request_id, lease_id, artifact[3], artifact[4], artifact[6]):
                return 409, {"error": "committed Phase 5A artifact identity mismatch"}
            response = dict(prior[1]); response["duplicate"] = True
            return 200, response
        metadata = body["metadata"]
        try:
            promotion = promote_phase5a_evidence(request_id, lease_id, run_id, contract_hash, body.get("sha256"), body.get("size_bytes"), metadata)
        except (OSError, ValueError):
            return 400, {"error": "invalid Phase 5A evidence"}
        retained_receipt = promotion["cleanup_receipt"]
        staging_receipt = promotion["staging_receipt"]
        if not isinstance(retained_receipt, dict) or not isinstance(staging_receipt, dict):
            return 500, {"error": "invalid Phase 5A promotion receipt"}
        artifact_id = str(uuid.uuid4())
        cur.execute("INSERT INTO activity.run_artifacts (id, execution_request_id, run_id, idempotency_key, artifact_type, protected_absolute_path, sha256, size_bytes, media_type, metadata) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (artifact_id, request_id, run_id, key, PHASE5A_ARTIFACT_TYPE, promotion["retained_path"], promotion["sha256"], promotion["size_bytes"], "application/json", json.dumps(promotion["metadata"])))
        response = {"claim_id": lease_id, "artifact_id": artifact_id, "duplicate": False}
        self._record_controller_command(cur, request_id, lease_id, "evidence", key, controller_id, controller_id, request_hash, response)
        promotions.append(_Phase5APromotion(
            retained_path=str(promotion["retained_path"]),
            retained_receipt=retained_receipt,
            staging_cleanup=lambda: cleanup_phase5a_staging(request_id, lease_id, staging_receipt),
        ))
        return 200, response

    def _controller_write(self, cur, path: str, body: dict, promotions: list[object] | None = None) -> tuple[int, dict]:
        if path == "/v1/controller/complete-cancellation":
            return self._phase5b_complete_cancellation(cur, body)
        routes = {"/v1/controller/claim": "claim", "/v1/controller/heartbeat": "heartbeat", "/v1/controller/running": "running", "/v1/controller/verifying": "verifying", "/v1/controller/evidence": "evidence", "/v1/controller/finish": "finish", "/v1/controller/fail": "fail"}
        command = routes.get(path)
        if command is None:
            return 404, {"error": "unknown controller endpoint"}
        request_id = body.get("request_id")
        contract_hash = body.get("contract_sha256")
        controller_id = body.get("controller_id")
        key = body.get("idempotency_key")
        if not (request_id and contract_hash and controller_id and key):
            return 400, {"error": "request_id, contract_sha256, controller_id, and idempotency_key are required"}
        try:
            request_id = _uuid(request_id, "request_id")
            _sha(contract_hash, "contract_sha256")
            _bounded(controller_id, "controller_id", 128)
            _idempotency_key(key)
            if command == "claim":
                _claim_token(body.get("claim_token"))
            else:
                _uuid(body.get("claim_id"), "claim_id")
                _claim_token(body.get("claim_token"))
        except ValueError as exc:
            return 400, {"error": str(exc)}
        cur.execute("SELECT contract_sha256, current_state, executor_profile FROM activity.execution_requests WHERE id=%s FOR UPDATE", (request_id,))
        request = cur.fetchone()
        if request is None:
            return 404, {"error": "execution request not found"}
        executor_profile = request[2] if len(request) > 2 else None
        if executor_profile is None:
            cur.execute("SELECT executor_profile FROM activity.execution_requests WHERE id=%s", (request_id,))
            profile_row = cur.fetchone()
            executor_profile = profile_row[0] if profile_row else None
        if request[0] != contract_hash:
            return 409, {"error": "contract hash mismatch"}
        claim_hash = token_hash(body["claim_token"]) if body.get("claim_token") else None
        request_hash = self._controller_request_hash(command, body, claim_hash)
        if executor_profile == PHASE5B_PROFILE and command in {"verifying", "finish", "fail"} and self._phase5b_cancellation(cur, request_id):
            return 409, {"error": "cancellation pending; preserve exclusion"}
        if command == "finish" and executor_profile == PHASE5B_PROFILE:
            return self._phase5b_finish(cur, request_id, body, request_hash)
        if command == "evidence" and executor_profile == PHASE5A_PROFILE:
            lease, _ = self._active_controller_lease(cur, request_id, contract_hash, body)
            if lease is None:
                return 409, {"error": "claim is expired, released, failed, or mismatched"}
            return self._phase5a_evidence(cur, request_id, contract_hash, controller_id, key, body, str(lease[0]), request[1], request_hash, promotions if promotions is not None else [])
        prior = self._controller_command(cur, request_id, command, key, controller_id, controller_id, request_hash)
        if prior is not None:
            return prior
        if command == "claim":
            token = body.get("claim_token", "")
            if not 32 <= len(token) <= 256 or request[1] != ExecutionState.QUEUED.value:
                return 409, {"error": "claim requires queued request and bounded claim token"}
            cur.execute("SELECT id FROM activity.execution_controller_leases WHERE execution_request_id=%s AND state='active'", (request_id,))
            if cur.fetchone():
                return 409, {"error": "request already has an active claim"}
            cur.execute("SELECT COALESCE(MAX(attempt_number), 0) + 1 FROM activity.execution_controller_leases WHERE execution_request_id=%s", (request_id,))
            attempt = int(cur.fetchone()[0])
            lease_id = str(uuid.uuid4())
            ttl = self._ttl()
            cur.execute("INSERT INTO activity.execution_controller_leases (id, execution_request_id, controller_id, attempt_number, claim_token_sha256, state, lease_expires_at) VALUES (%s,%s,%s,%s,%s,'active',now() + (%s * interval '1 second')) RETURNING lease_expires_at", (lease_id, request_id, controller_id, attempt, claim_hash, ttl))
            claim_expiry = cur.fetchone()[0]
            _transition(cur, request_id, request[1], ExecutionState.ALLOCATED, controller_id, f"controller:{lease_id}:allocated", {"lease_id": lease_id, "attempt_number": attempt})
            response = {"claim_id": lease_id, "attempt_number": attempt, "state": ExecutionState.ALLOCATED.value, "duplicate": False}
            if executor_profile in {PHASE5A_PROFILE, PHASE5B_PROFILE}:
                response["lease_expires_at"] = self._lease_expiry(claim_expiry)
            self._record_controller_command(cur, request_id, lease_id, command, key, controller_id, controller_id, request_hash, response)
            return 200, response
        lease, claim_hash = self._active_controller_lease(cur, request_id, contract_hash, body)
        if lease is None:
            return 409, {"error": "claim is expired, released, failed, or mismatched"}
        lease_id = str(lease[0])
        response: dict = {}
        if command == "heartbeat":
            ttl = self._ttl()
            cur.execute("UPDATE activity.execution_controller_leases SET last_heartbeat_at=now(), lease_expires_at=now() + (%s * interval '1 second') WHERE id=%s AND state='active' AND lease_expires_at > now() RETURNING id, lease_expires_at", (ttl, lease_id))
            heartbeat_row = cur.fetchone()
            if heartbeat_row is None:
                return 409, {"error": "claim expired during heartbeat"}
            response = {"claim_id": lease_id, "state": request[1], "duplicate": False}
            if executor_profile in {PHASE5A_PROFILE, PHASE5B_PROFILE}:
                response["lease_expires_at"] = self._lease_expiry(heartbeat_row[1])
        elif command in {"running", "verifying", "finish"}:
            targets = {"running": ExecutionState.RUNNING, "verifying": ExecutionState.VERIFYING, "finish": ExecutionState.AWAITING_REVIEW}
            target = targets[command]
            if command == "running":
                if request[1] != ExecutionState.ALLOCATED.value:
                    return 409, {"error": "running requires allocated state"}
                cur.execute("SELECT id FROM activity.runs WHERE execution_request_id=%s", (request_id,))
                run = cur.fetchone()
                run_id = str(run[0]) if run else str(uuid.uuid4())
                if run is None:
                    source_interface = PHASE5A_SOURCE_INTERFACE if executor_profile == PHASE5A_PROFILE else (PHASE5B_SOURCE_INTERFACE if executor_profile == PHASE5B_PROFILE else "phase4b-fake-controller")
                    cur.execute("INSERT INTO activity.runs (id, task_id, execution_request_id, actor, source_interface, status, started_at) SELECT %s, task_id, %s, %s, %s, 'running', now() FROM activity.execution_requests WHERE id=%s", (run_id, request_id, controller_id, source_interface, request_id))
                response = {"claim_id": lease_id, "run_id": run_id, "state": target.value, "duplicate": False}
            elif command == "verifying":
                if request[1] != ExecutionState.RUNNING.value:
                    return 409, {"error": "verifying requires running state"}
                cur.execute("SELECT id FROM activity.runs WHERE execution_request_id=%s", (request_id,))
                run = cur.fetchone()
                if run is None:
                    return 409, {"error": "associated run is required"}
                cur.execute("UPDATE activity.runs SET status='verifying' WHERE id=%s", (run[0],))
                response = {"claim_id": lease_id, "state": target.value, "duplicate": False}
            else:
                if request[1] != ExecutionState.VERIFYING.value:
                    return 409, {"error": "finish requires verifying state"}
                cur.execute("SELECT id FROM activity.runs WHERE execution_request_id=%s", (request_id,))
                run = cur.fetchone()
                if run is None:
                    return 409, {"error": "associated run is required"}
                required_artifact = PHASE5A_ARTIFACT_TYPE if executor_profile == PHASE5A_PROFILE else "phase4b_fake_controller_result"
                cur.execute("SELECT id FROM activity.run_artifacts WHERE execution_request_id=%s AND run_id=%s AND artifact_type=%s", (request_id, run[0], required_artifact))
                if cur.fetchone() is None:
                    return 409, {"error": "matching executor evidence is required" if executor_profile == PHASE5A_PROFILE else "fake-controller evidence is required"}
                cur.execute("UPDATE activity.runs SET status='awaiting_review', finished_at=now() WHERE id=%s", (run[0],))
                _transition(cur, request_id, request[1], target, controller_id, f"controller:{lease_id}:awaiting_review", {})
                cur.execute("UPDATE activity.execution_controller_leases SET state='released', released_at=now() WHERE id=%s", (lease_id,))
                response = {"claim_id": lease_id, "state": target.value, "duplicate": False}
            if command != "finish":
                _transition(cur, request_id, request[1], target, controller_id, f"controller:{lease_id}:{target.value}", {})
        elif command == "evidence":
            path_value = body.get("path", "")
            metadata = body.get("metadata")
            expected_path = f"{PHASE4B_STAGING_ROOT}/{request_id}/{lease_id}.json"
            exact_metadata = {"schema_name": "phase4b-fake-controller-result", "schema_version": "1", "controller_id": controller_id, "claim_id": lease_id, "outcome": "pass"}
            if request[1] not in {ExecutionState.RUNNING.value, ExecutionState.VERIFYING.value} or body.get("artifact_type") != "phase4b_fake_controller_result" or body.get("media_type") != "application/json" or not isinstance(metadata, dict):
                return 400, {"error": "invalid fake-controller evidence"}
            if path_value != expected_path or posixpath.normpath(path_value) != path_value:
                return 400, {"error": "invalid protected evidence path"}
            digest, size = body.get("sha256", ""), body.get("size_bytes")
            if metadata != exact_metadata or not _HASH_RE.fullmatch(digest) or not isinstance(size, int) or not 0 < size <= 65536:
                return 400, {"error": "invalid evidence metadata"}
            cur.execute("SELECT id FROM activity.runs WHERE execution_request_id=%s", (request_id,))
            if cur.fetchone() is None:
                return 409, {"error": "associated run is required"}
            cur.execute("SELECT id FROM activity.run_artifacts WHERE execution_request_id=%s AND artifact_type='phase4b_fake_controller_result'", (request_id,))
            if cur.fetchone() is not None:
                return 409, {"error": "fake-controller evidence already exists"}
            promotion = promote_phase4b_evidence(
                path_value, request_id, lease_id, controller_id, digest, size
            )
            if promotions is not None:
                promotions.append((promotion["retained_path"], promotion["cleanup_receipt"]))
            artifact_id = str(uuid.uuid4())
            cur.execute("INSERT INTO activity.run_artifacts (id, execution_request_id, run_id, idempotency_key, artifact_type, protected_absolute_path, sha256, size_bytes, media_type, metadata) VALUES (%s,%s,(SELECT id FROM activity.runs WHERE execution_request_id=%s),%s,%s,%s,%s,%s,%s,%s)", (artifact_id, request_id, request_id, key, body["artifact_type"], promotion["retained_path"], promotion["sha256"], promotion["size_bytes"], body["media_type"], json.dumps(promotion["metadata"])))
            response = {"claim_id": lease_id, "artifact_id": artifact_id, "duplicate": False}
        else:
            reason = body.get("failure_classification")
            allowed_reasons = {"timeout", "lease_expired", "protocol_error", "evidence_error", "controller_error", "work_order_rejected", "repository_binding_failed", "instruction_validation_failed", "repository_policy_violation", "model_timeout", "model_error", "malformed_model_response", "tool_limit_exceeded", "output_limit_exceeded", "validation_failed", "validation_timeout", "git_policy_violation", "git_commit_failed", "evidence_generation_failed", "evidence_publication_failed", "unsafe_worktree", "unsafe_instruction", "replay_conflict", "internal_error"}
            if command == "fail" and (request[1] not in {ExecutionState.ALLOCATED.value, ExecutionState.RUNNING.value, ExecutionState.VERIFYING.value} or reason not in allowed_reasons):
                return 400, {"error": "invalid failure classification or state"}
            if command == "fail":
                _transition(cur, request_id, request[1], ExecutionState.FAILED, controller_id, f"controller:{lease_id}:failed", {"failure_classification": reason})
                _transition(cur, request_id, ExecutionState.FAILED.value, ExecutionState.CLOSING, controller_id, f"controller:{lease_id}:closing", {})
                _transition(cur, request_id, ExecutionState.CLOSING.value, ExecutionState.CLOSED, controller_id, f"controller:{lease_id}:closed", {})
                cur.execute("UPDATE activity.runs SET status='failed', finished_at=now() WHERE execution_request_id=%s", (request_id,))
                cur.execute("UPDATE activity.execution_controller_leases SET state='failed', released_at=now(), failure_reason=%s WHERE id=%s", (reason, lease_id))
                response = {"claim_id": lease_id, "state": ExecutionState.CLOSED.value, "duplicate": False}
        if command in {"heartbeat", "running", "verifying", "evidence", "finish", "fail"}:
            self._record_controller_command(cur, request_id, lease_id, command, key, controller_id, controller_id, request_hash, response)
        return 200, response
    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if not self._authorized("controller" if path.startswith("/v1/controller/") else "operator"):
            return
        if int(self.headers.get("Content-Length", "0")) > 65536:
            self._json(413, {"error": "payload too large"})
            return
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
            path = urlparse(self.path).path
            if path.startswith("/v1/controller/"):
                try:
                    db = connect()
                except Exception:
                    try:
                        self._json(500, {"error": "internal server error"})
                    except Exception:
                        pass
                    return
                try:
                    def write(promotions):
                        with db.cursor() as cur:
                            return self._controller_write(cur, path, body, promotions)

                    _run_controller_transaction(db, write, self._json)
                finally:
                    try:
                        db.close()
                    except Exception:
                        pass
                return
            if path.startswith("/v1/execution-requests/") and path.endswith("/review"):
                db = connect()
                try:
                    with db.cursor() as cur:
                        status, result = self._review(cur, path.removeprefix("/v1/execution-requests/").removesuffix("/review"), body)
                    _commit_then_respond(db, status, result, self._json)
                except ValueError as exc:
                    db.rollback()
                    self._json(400, {"error": type(exc).__name__})
                except Exception as exc:
                    db.rollback()
                    self._json(500, {"error": type(exc).__name__})
                finally:
                    db.close()
                return
            if path.startswith("/v1/execution-requests/") and path.endswith("/recover-expired-controller"):
                db = connect()
                try:
                    with db.cursor() as cur:
                        status, result = self._recover(cur, path.removeprefix("/v1/execution-requests/").removesuffix("/recover-expired-controller"), body)
                    _commit_then_respond(db, status, result, self._json)
                except ValueError as exc:
                    db.rollback()
                    self._json(400, {"error": type(exc).__name__})
                except Exception as exc:
                    db.rollback()
                    self._json(500, {"error": type(exc).__name__})
                finally:
                    db.close()
                return
            phase4a_write = path == "/v1/execution-requests" or (
                path.startswith("/v1/execution-requests/")
                and (path.endswith("/approve") or path.endswith("/cancel"))
            )
            if phase4a_write:
                db = connect()
                try:
                    with db.cursor() as cur:
                        if path == "/v1/execution-requests":
                            status, result = self._submit(cur, body)
                        elif path.endswith("/approve"):
                            status, result = self._approve(cur, path.removeprefix("/v1/execution-requests/").removesuffix("/approve"), body)
                        else:
                            status, result = self._cancel(cur, path.removeprefix("/v1/execution-requests/").removesuffix("/cancel"), body)
                    _commit_then_respond(db, status, result, self._json)
                except (ContractError, ProfileError, KeyError, ValueError) as exc:
                    try:
                        db.rollback()
                    finally:
                        self._json(400, {"error": type(exc).__name__, "detail": str(exc)})
                except Exception as exc:
                    try:
                        db.rollback()
                    finally:
                        self._json(400, {"error": type(exc).__name__})
                finally:
                    db.close()
                return
            with connect() as db, db.cursor() as cur:
                if path == "/v1/tasks":
                    cur.execute("INSERT INTO activity.tasks (id, task_key, title, description, origin_type, state, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, 'draft', now(), now()) ON CONFLICT (task_key) DO NOTHING RETURNING task_key", (uuid.uuid4(), body["task_key"], body["title"], body["description"], body["origin_type"]))
                    self._json(200, {"task_key": cur.fetchone()[0] if cur.rowcount else body["task_key"]})
                    return
                if path == "/v1/runs":
                    cur.execute("SELECT id FROM activity.tasks WHERE task_key=%s", (body["task_key"],))
                    task = cur.fetchone()
                    if task is None:
                        self._json(404, {"error": "task not found"})
                        return
                    run_id = body.get("run_id", str(uuid.uuid4()))
                    cur.execute("INSERT INTO activity.runs (id, task_id, actor, source_interface, status, started_at) VALUES (%s, %s, %s, %s, 'running', now()) ON CONFLICT (id) DO NOTHING RETURNING id", (run_id, task[0], body["actor"], body["source_interface"]))
                    inserted = cur.fetchone()
                    self._json(200, {"run_id": str(inserted[0]) if inserted else run_id, "duplicate": inserted is None})
                    return
                if path == "/v1/events":
                    if int(body["sequence_number"]) != 1:
                        cur.execute("SELECT COALESCE(MAX(sequence_number), 0) FROM activity.events WHERE run_id=%s", (body["run_id"],))
                        if int(body["sequence_number"]) != int(cur.fetchone()[0]) + 1:
                            self._json(409, {"error": "sequence rejected"})
                            return
                    cur.execute("INSERT INTO activity.events (run_id, sequence_number, idempotency_key, event_type, payload, created_at) VALUES (%s,%s,%s,%s,%s,now()) ON CONFLICT (run_id, idempotency_key) DO NOTHING RETURNING sequence_number", (body["run_id"], body["sequence_number"], body["idempotency_key"], body["event_type"], json.dumps(body["payload"])))
                    self._json(200, {"sequence_number": body["sequence_number"], "duplicate": cur.fetchone() is None})
                    return
                if path == "/v1/runs/heartbeat":
                    cur.execute("SELECT 1 FROM activity.runs WHERE id=%s AND status='running'", (body["run_id"],))
                    if cur.fetchone() is None:
                        self._json(404, {"error": "run not found or not running"})
                        return
                    self._json(200, {"run_id": body["run_id"], "status": "running"})
                    return
                if path == "/v1/runs/complete":
                    cur.execute("UPDATE activity.runs SET status=%s, finished_at=now() WHERE id=%s AND status='running'", (body["status"], body["run_id"]))
                    if cur.rowcount != 1:
                        cur.execute("SELECT status FROM activity.runs WHERE id=%s", (body["run_id"],))
                        existing = cur.fetchone()
                        if existing and existing[0] == body["status"]:
                            self._json(200, {"run_id": body["run_id"], "status": body["status"], "duplicate": True})
                        else:
                            self._json(404, {"error": "run not found or already complete"})
                    else:
                        self._json(200, {"run_id": body["run_id"], "status": body["status"]})
                    return
                self._json(404, {"error": "not found"})
        except (ContractError, ProfileError, KeyError, ValueError) as exc:
            self._json(400, {"error": type(exc).__name__, "detail": str(exc)})
        except Exception as exc:
            self._json(400, {"error": type(exc).__name__})

    def _review(self, cur, request_id: str, body: dict) -> tuple[int, dict]:
        actor, decision, gate = body.get("actor"), body.get("decision"), body.get("approval_gate")
        key, contract_hash = body.get("idempotency_key"), body.get("contract_sha256")
        try:
            _uuid(request_id, "request_id")
            _bounded(actor, "actor", 128)
            _idempotency_key(key)
            _sha(contract_hash, "contract_sha256")
        except ValueError as exc:
            return 400, {"error": str(exc)}
        if gate != "review" or decision not in {"approved", "rejected"}:
            return 400, {"error": "review approval requires approval_gate=review, actor, decision, idempotency_key, contract_sha256"}
        cur.execute("SELECT contract_sha256, current_state, executor_profile FROM activity.execution_requests WHERE id=%s FOR UPDATE", (request_id,))
        request = cur.fetchone()
        if request is None or request[0] != contract_hash:
            return 409, {"error": "request not found or contract hash mismatch"}
        cur.execute("SELECT actor, decision, approval_gate, contract_sha256 FROM activity.execution_approvals WHERE execution_request_id=%s AND approval_gate='review' AND idempotency_key=%s", (request_id, key))
        prior = cur.fetchone()
        if prior:
            if prior == (actor, decision, gate, contract_hash):
                return 200, {"request_id": request_id, "state": ExecutionState.CLOSED.value, "duplicate": True}
            return 409, {"error": "review idempotency key conflict"}
        if request[1] != ExecutionState.AWAITING_REVIEW.value:
            return 409, {"error": "review is not legal in current state"}
        cur.execute("SELECT id, source_interface FROM activity.runs WHERE execution_request_id=%s", (request_id,))
        runs = cur.fetchall()
        if len(runs) != 1:
            return 409, {"error": "associated run is required"}
        run_id, source_interface = runs[0]
        if request[2] == PHASE5A_PROFILE:
            if source_interface != "phase5a-model-free-executor":
                return 409, {"error": "Phase 5A run source interface mismatch"}
            artifact_type = PHASE5A_ARTIFACT_TYPE
            missing_error = "Phase 5A evidence is required"
        elif request[2] == "repository-review-v1":
            artifact_type = "phase4b_fake_controller_result"
            missing_error = "fake-controller evidence is required"
        else:
            return 409, {"error": "unsupported executor profile for review"}
        cur.execute("SELECT id FROM activity.run_artifacts WHERE execution_request_id=%s AND run_id=%s AND artifact_type=%s", (request_id, run_id, artifact_type))
        if cur.fetchone() is None:
            return 409, {"error": missing_error}
        target = ExecutionState.APPROVED if decision == "approved" else ExecutionState.REJECTED
        cur.execute("INSERT INTO activity.execution_approvals (id, execution_request_id, approval_gate, actor, decision, contract_sha256, idempotency_key) VALUES (%s,%s,%s,%s,%s,%s,%s)", (uuid.uuid4(), request_id, gate, actor, decision, contract_hash, key))
        _transition(cur, request_id, request[1], target, actor, f"review:{key}:{target.value}", {"approval_gate": gate, "decision": decision})
        _transition(cur, request_id, target.value, ExecutionState.CLOSING, actor, f"review:{key}:closing", {})
        _transition(cur, request_id, ExecutionState.CLOSING.value, ExecutionState.CLOSED, actor, f"review:{key}:closed", {})
        cur.execute("UPDATE activity.runs SET status=%s WHERE id=%s", ("succeeded" if decision == "approved" else "rejected", run_id))
        return 200, {"request_id": request_id, "state": ExecutionState.CLOSED.value, "duplicate": False}

    def _recover(self, cur, request_id: str, body: dict) -> tuple[int, dict]:
        actor, key, contract_hash, claim_id = (body.get(name) for name in ("actor", "idempotency_key", "contract_sha256", "claim_id"))
        if set(body) - _COMMAND_FIELDS["recover_expired"]:
            return 400, {"error": "invalid recovery request"}
        try:
            _uuid(request_id, "request_id")
            _uuid(claim_id, "claim_id")
            _bounded(actor, "actor", 128)
            _idempotency_key(key)
            _sha(contract_hash, "contract_sha256")
        except ValueError as exc:
            return 400, {"error": str(exc)}
        actor, key, contract_hash, claim_id = str(actor), str(key), str(contract_hash), str(claim_id)
        cur.execute("SELECT contract_sha256, current_state FROM activity.execution_requests WHERE id=%s FOR UPDATE", (request_id,))
        request = cur.fetchone()
        if request is None or request[0] != contract_hash:
            return 409, {"error": "request not found or contract hash mismatch"}
        cur.execute("SELECT controller_id FROM activity.execution_controller_leases WHERE id=%s AND execution_request_id=%s", (claim_id, request_id))
        controller_row = cur.fetchone()
        controller_id = controller_row[0] if controller_row else "unknown"
        cur.execute("SELECT state, lease_expires_at, lease_expires_at <= now() FROM activity.execution_controller_leases WHERE id=%s AND execution_request_id=%s FOR UPDATE", (claim_id, request_id))
        lease = cur.fetchone()
        request_hash = self._controller_request_hash("recover_expired", body)
        prior = self._controller_command(cur, request_id, "recover_expired", key, actor, controller_id, request_hash)
        if prior is not None:
            return prior
        if lease is None or lease[0] != "active" or not lease[2]:
            return 409, {"error": "claim is not active or expired"}
        _transition(cur, request_id, request[1], ExecutionState.FAILED, actor, f"recovery:{key}:failed", {"claim_id": claim_id})
        _transition(cur, request_id, ExecutionState.FAILED.value, ExecutionState.CLOSING, actor, f"recovery:{key}:closing", {})
        _transition(cur, request_id, ExecutionState.CLOSING.value, ExecutionState.CLOSED, actor, f"recovery:{key}:closed", {})
        cur.execute("UPDATE activity.execution_requests SET finished_at=now() WHERE id=%s", (request_id,))
        cur.execute("UPDATE activity.runs SET status='failed', finished_at=now() WHERE execution_request_id=%s", (request_id,))
        cur.execute("UPDATE activity.execution_controller_leases SET state='expired', released_at=now(), failure_reason='lease_expired' WHERE id=%s AND execution_request_id=%s", (claim_id, request_id))
        response = {"request_id": request_id, "claim_id": claim_id, "state": ExecutionState.CLOSED.value, "duplicate": False}
        self._record_controller_command(cur, request_id, claim_id, "recover_expired", key, actor, controller_id, request_hash, response)
        return 200, response

    def _submit(self, cur, body: dict) -> tuple[int, dict]:
        try:
            normalized, contract_hash = normalized_contract_sha256(body["contract"])
        except (KeyError, ContractError, ProfileError) as exc:
            raise ValueError(str(exc)) from exc
        key = _idempotency_key(normalized["idempotency_key"])
        cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (key,))
        cur.execute("SELECT id, contract_sha256, current_state FROM activity.execution_requests WHERE idempotency_key=%s FOR UPDATE", (key,))
        existing = cur.fetchone()
        if existing:
            if existing[1] != contract_hash:
                return 409, {"error": "idempotency key conflicts with existing contract"}
            else:
                return 200, {"request_id": str(existing[0]), "state": existing[2], "contract_sha256": existing[1], "duplicate": True}
        cur.execute("SELECT id FROM activity.tasks WHERE task_key=%s", (normalized["task_key"],))
        task = cur.fetchone()
        if task is None:
            return 404, {"error": "task not found"}
        request_id = str(uuid.uuid4())
        cur.execute("INSERT INTO activity.execution_requests (id, idempotency_key, task_id, operation, workflow_template, executor_profile, normalized_contract, contract_sha256, current_state, requested_by, validated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())", (request_id, key, task[0], normalized["operation"], normalized["workflow_template"], normalized["executor_profile"], json.dumps(normalized), contract_hash, ExecutionState.SUBMITTED.value, normalized["requested_by"]))
        _record_event(cur, request_id, 1, f"{key}:submitted", "state_entered", None, ExecutionState.SUBMITTED.value, normalized["requested_by"], {"contract_sha256": contract_hash})
        _transition(cur, request_id, ExecutionState.SUBMITTED.value, ExecutionState.VALIDATED, normalized["requested_by"], f"{key}:validated", {})
        _transition(cur, request_id, ExecutionState.VALIDATED.value, ExecutionState.AWAITING_EXECUTION_APPROVAL, normalized["requested_by"], f"{key}:awaiting_execution_approval", {})
        return 200, {"request_id": request_id, "state": ExecutionState.AWAITING_EXECUTION_APPROVAL.value, "contract_sha256": contract_hash, "duplicate": False}

    def _approve(self, cur, request_id: str, body: dict) -> tuple[int, dict]:
        actor = body.get("actor")
        decision = body.get("decision")
        gate = body.get("approval_gate")
        approval_key = body.get("idempotency_key")
        contract_hash = body.get("contract_sha256")
        if not all((actor, decision, gate, approval_key, contract_hash)):
            raise ValueError("actor, decision, approval_gate, idempotency_key, and contract_sha256 are required")
        _uuid(request_id, "request_id")
        _bounded(actor, "actor", 128)
        _idempotency_key(approval_key)
        _sha(contract_hash, "contract_sha256")
        cur.execute("SELECT contract_sha256, current_state FROM activity.execution_requests WHERE id=%s FOR UPDATE", (request_id,))
        request = cur.fetchone()
        if request is None:
            return 404, {"error": "execution request not found"}
        cur.execute("SELECT actor, decision, approval_gate, contract_sha256 FROM activity.execution_approvals WHERE execution_request_id=%s AND idempotency_key=%s", (request_id, approval_key))
        prior = cur.fetchone()
        if prior:
            if prior == (actor, decision, gate, contract_hash):
                return 200, {"request_id": request_id, "state": "queued" if decision == "approved" else "rejected", "decision": decision, "duplicate": True}
            return 409, {"error": "approval idempotency key conflict"}
        if gate != "execution" or decision not in {"approved", "rejected"}:
            return 400, {"error": "Phase 4A accepts only execution approval with approved or rejected decision"}
        if request[0] != contract_hash:
            return 409, {"error": "stale contract approval"}
        target = ExecutionState.QUEUED if decision == "approved" else ExecutionState.REJECTED
        try:
            ExecutionStateMachine(_state(request[1])).transition(target)
        except ValueError:
            return 409, {"error": "approval is not legal in current state"}
        cur.execute("INSERT INTO activity.execution_approvals (id, execution_request_id, approval_gate, actor, decision, contract_sha256, idempotency_key) VALUES (%s,%s,%s,%s,%s,%s,%s)", (uuid.uuid4(), request_id, gate, actor, decision, contract_hash, approval_key))
        _transition(cur, request_id, request[1], target, actor, f"approval:{approval_key}", {"approval_gate": gate, "decision": decision, "contract_sha256": contract_hash})
        return 200, {"request_id": request_id, "state": target.value, "decision": decision, "duplicate": False}

    def _phase5b_cancellation(self, cur, request_id: str) -> dict | None:
        cur.execute("SELECT metadata FROM activity.execution_request_events WHERE execution_request_id=%s AND idempotency_key='phase5b:cancellation:requested'", (request_id,))
        row = cur.fetchone()
        return row[0] if row else None

    def _phase5b_complete_cancellation(self, cur, body: dict) -> tuple[int, dict]:
        required = {'request_id', 'contract_sha256', 'controller_id', 'claim_id', 'claim_token', 'idempotency_key', 'stop_proof', 'owner'}
        if set(body) != required:
            return 400, {'error': 'invalid cancellation completion fields'}
        request_id = _uuid(body['request_id'], 'request_id')
        _sha(body['contract_sha256']); _uuid(body['claim_id'], 'claim_id')
        _claim_token(body['claim_token']); _bounded(body['controller_id'], 'controller_id', 128)
        _idempotency_key(body['idempotency_key'])
        cur.execute("SELECT contract_sha256, current_state, executor_profile FROM activity.execution_requests WHERE id=%s FOR UPDATE", (request_id,))
        request = cur.fetchone()
        if not request or request[0] != body['contract_sha256'] or request[2] != PHASE5B_PROFILE:
            return 409, {'error': 'cancellation request binding mismatch'}
        intent = self._phase5b_cancellation(cur, request_id)
        if not intent or intent.get('claim_id') != body['claim_id'] or intent.get('contract_sha256') != body['contract_sha256']:
            return 409, {'error': 'exact cancellation intent required'}
        proof, owner = body['stop_proof'], body['owner']
        if (not isinstance(proof, dict) or set(proof) != {'writer_identity_sha256', 'stopped', 'reconciliation_required', 'work_order_sha256'}
                or proof['stopped'] is not True or proof['reconciliation_required'] is not False
                or not isinstance(owner, dict)):
            return 409, {'error': 'verified stop proof required'}
        _sha(proof['writer_identity_sha256']); _sha(proof['work_order_sha256'])
        encoded = json.dumps(owner, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
        if hashlib.sha256(encoded).hexdigest() != proof['writer_identity_sha256']:
            return 409, {'error': 'stop owner mismatch'}
        cur.execute("SELECT controller_lease_id, run_id, allocation_id, work_order_sha256 FROM activity.phase5b_execution_bindings WHERE execution_request_id=%s", (request_id,))
        binding = cur.fetchone()
        if (not binding or str(binding[0]) != body['claim_id'] or str(binding[1]) != intent['run_id']
                or str(binding[2]) != owner.get('allocation_id') or binding[3] != proof['work_order_sha256']):
            return 409, {'error': 'stop execution binding mismatch'}
        metadata = {'intent': intent, 'stop_proof': proof, 'owner': owner,
                    'controller_id': body['controller_id'], 'claim_token_sha256': token_hash(body['claim_token']),
                    'idempotency_key': body['idempotency_key']}
        cur.execute("SELECT metadata FROM activity.execution_request_events WHERE execution_request_id=%s AND idempotency_key='phase5b:cancellation:cancelled'", (request_id,))
        prior = cur.fetchone()
        if prior:
            return (200, {'state': 'closed', 'duplicate': True}) if prior[0] == metadata and request[1] == 'closed' else (409, {'error': 'cancellation completion conflict'})
        lease, _ = self._active_controller_lease(cur, request_id, request[0], body)
        if lease is None or request[1] != 'running':
            return 409, {'error': 'active running claim required; preserve exclusion'}
        cur.execute("SELECT 1 FROM activity.phase5b_execution_writer_leases WHERE allocation_id=%s AND writer_id=%s AND generation=%s AND fence_sha256=%s AND execution_request_id=%s AND controller_lease_id=%s AND run_id=%s AND state='active' AND lease_expires_at > now() FOR UPDATE", (owner.get('allocation_id'), owner.get('writer_id'), owner.get('generation'), owner.get('fence_sha256'), request_id, body['claim_id'], intent['run_id']))
        if cur.fetchone() is None:
            return 409, {'error': 'exact active writer required; preserve exclusion'}
        for current, target in (('running', ExecutionState.CANCELLED), ('cancelled', ExecutionState.CLOSING), ('closing', ExecutionState.CLOSED)):
            _transition(cur, request_id, current, target, body['controller_id'], 'phase5b:cancellation:' + target.value, metadata)
        cur.execute("UPDATE activity.runs SET status='cancelled', finished_at=now() WHERE id=%s AND execution_request_id=%s", (intent['run_id'], request_id))
        cur.execute("UPDATE activity.execution_controller_leases SET state='released', released_at=now() WHERE id=%s", (body['claim_id'],))
        cur.execute("UPDATE activity.execution_requests SET finished_at=now() WHERE id=%s", (request_id,))
        return 200, {'state': 'closed', 'duplicate': False}

    def _cancel(self, cur, request_id: str, body: dict) -> tuple[int, dict]:
        actor = body.get("actor")
        cancel_key = body.get("idempotency_key")
        contract_hash = body.get("contract_sha256")
        if not all((actor, cancel_key, contract_hash)):
            raise ValueError("actor, idempotency_key, and contract_sha256 are required")
        _uuid(request_id, "request_id")
        _bounded(actor, "actor", 128)
        _idempotency_key(cancel_key)
        _sha(contract_hash, "contract_sha256")
        cur.execute("SELECT contract_sha256, current_state FROM activity.execution_requests WHERE id=%s FOR UPDATE", (request_id,))
        request = cur.fetchone()
        if request is None:
            return 404, {"error": "execution request not found"}
        if request[0] != contract_hash:
            return 409, {"error": "stale contract cancellation"}
        intent = self._phase5b_cancellation(cur, request_id)
        if intent:
            same = all(intent.get(k) == v for k, v in {'actor': actor, 'contract_sha256': contract_hash, 'idempotency_key': cancel_key}.items())
            return (200 if request[1] == 'closed' else 202, {'request_id': request_id, 'state': request[1], 'cancellation_requested': True, 'duplicate': True}) if same else (409, {'error': 'cancellation intent conflict'})
        if request[1] == 'running':
            cur.execute("SELECT executor_profile FROM activity.execution_requests WHERE id=%s", (request_id,))
            profile = cur.fetchone()
            cur.execute("SELECT l.id, run.id FROM activity.execution_controller_leases l JOIN activity.runs run ON run.execution_request_id=l.execution_request_id WHERE l.execution_request_id=%s AND l.state='active' AND l.lease_expires_at > now()", (request_id,))
            live = cur.fetchone()
            if not profile or profile[0] != PHASE5B_PROFILE or not live:
                return 409, {'error': 'active Phase 5B running claim required'}
            metadata = {'actor': actor, 'contract_sha256': contract_hash, 'idempotency_key': cancel_key, 'claim_id': str(live[0]), 'run_id': str(live[1])}
            _record_event(cur, request_id, _next_sequence(cur, request_id), 'phase5b:cancellation:requested', 'cancellation_requested', 'running', 'running', actor, metadata)
            return 202, {'request_id': request_id, 'state': 'running', 'cancellation_requested': True, 'duplicate': False}
        cancel_event_key = f"cancellation:{cancel_key}:cancelled"
        cur.execute("SELECT actor, metadata FROM activity.execution_request_events WHERE execution_request_id=%s AND idempotency_key=%s", (request_id, cancel_event_key))
        prior = cur.fetchone()
        if prior:
            metadata = prior[1] or {}
            if metadata.get("actor") == actor and metadata.get("contract_sha256") == contract_hash and request[1] == ExecutionState.CLOSED.value:
                return 200, {"request_id": request_id, "state": ExecutionState.CLOSED.value, "duplicate": True}
            return 409, {"error": "cancellation idempotency key conflict"}
        if request[1] not in {ExecutionState.SUBMITTED.value, ExecutionState.VALIDATED.value, ExecutionState.AWAITING_EXECUTION_APPROVAL.value, ExecutionState.QUEUED.value}:
            return 409, {"error": "cancellation is not legal after resource allocation or terminal decision"}
        metadata = {"actor": actor, "contract_sha256": contract_hash, "cancellation_idempotency_key": cancel_key}
        current = request[1]
        _transition(cur, request_id, current, ExecutionState.CANCELLED, actor, cancel_event_key, metadata)
        _transition(cur, request_id, ExecutionState.CANCELLED.value, ExecutionState.CLOSING, actor, f"cancellation:{cancel_key}:closing", metadata)
        _transition(cur, request_id, ExecutionState.CLOSING.value, ExecutionState.CLOSED, actor, f"cancellation:{cancel_key}:closed", metadata)
        cur.execute("UPDATE activity.execution_requests SET finished_at=now() WHERE id=%s", (request_id,))
        return 200, {"request_id": request_id, "state": ExecutionState.CLOSED.value, "duplicate": False}

    def log_message(self, format: str, *args) -> None:
        return


class PostgresPhase5BAdapter:
    """Controller-facing PostgreSQL protocol bridge.

    The connection factory is injected for tests and deployment wiring. This
    class owns the short-lived claim token only in memory; the database stores
    only its hash through the existing controller command path.
    """

    def __init__(self, connection_factory: Callable[[], object], *, controller_id: str, handler: Handler | None = None, claim_token_secret: bytes | None = None) -> None:
        self.connection_factory = connection_factory
        self.controller_id = controller_id
        self.handler = handler or object.__new__(Handler)
        self.claim_token_secret = claim_token_secret
        self._tokens: dict[str, str] = {}
        self._claims: dict[str, dict] = {}
        self._allocations: dict[str, HandoffDescriptor] = {}
        self._orders: dict[str, dict] = {}

    def _transaction(self, operation: Callable[[object], tuple[int, dict]], *, read_only: bool = False, missing_ok: bool = False) -> dict | None:
        db = self.connection_factory()
        cur = None
        try:
            cur = db.cursor()
            status, response = operation(cur)
            if status == 404 and missing_ok:
                db.rollback()
                return None
            if status >= 400:
                db.rollback()
                raise RuntimeError(response.get("error", "PostgreSQL adapter operation failed"))
            db.rollback() if read_only else db.commit()
            return response
        finally:
            try:
                if cur is not None:
                    cur.close()
            finally:
                db.close()

    def _command(self, path: str, body: dict) -> dict:
        return self._transaction(lambda cur: self.handler._controller_write(cur, path, body, []))

    def claim(self, request_id: str, contract_sha256: str, controller_id: str, attempt_number: int) -> dict:
        if controller_id != self.controller_id or type(attempt_number) is not int or attempt_number != 1:
            raise RuntimeError("controller_identity_or_attempt_mismatch")
        if self.claim_token_secret is None:
            raise RuntimeError("claim_token_derivation_secret_required")
        material = f"phase5b:{request_id}:{controller_id}:{attempt_number}".encode()
        token = base64.urlsafe_b64encode(hmac.new(self.claim_token_secret, material, hashlib.sha256).digest()).decode().rstrip("=")
        key = f"{request_id}:attempt:{attempt_number}:claim"
        response = self._command("/v1/controller/claim", {"request_id": request_id, "contract_sha256": contract_sha256, "controller_id": controller_id, "idempotency_key": key, "claim_token": token})
        self._tokens[request_id] = token
        claim = {**response, "request_id": request_id, "contract_sha256": contract_sha256, "controller_id": controller_id, "claim_token": token}
        self._claims[request_id] = claim
        return claim

    def _claim_body(self, claim: dict, key: str) -> dict:
        return {"request_id": claim["request_id"], "contract_sha256": claim["contract_sha256"], "controller_id": claim["controller_id"], "idempotency_key": key, "claim_id": claim["claim_id"], "claim_token": claim["claim_token"]}

    def running(self, claim: dict) -> dict:
        response = self._command("/v1/controller/running", self._claim_body(claim, f"{claim['request_id']}:attempt:{claim['attempt_number']}:running"))
        claim.update(response)
        self._claims[claim["request_id"]] = claim
        return dict(claim)

    def verifying(self, claim: dict) -> dict:
        response = self._command("/v1/controller/verifying", self._claim_body(claim, f"{claim['request_id']}:attempt:{claim['attempt_number']}:verifying"))
        return {**claim, **response}

    def bind_allocation(self, request_id: str, allocation: Any) -> HandoffDescriptor:
        descriptor = allocation if isinstance(allocation, HandoffDescriptor) else HandoffDescriptor(**(allocation.as_dict() if hasattr(allocation, "as_dict") else dict(allocation)))
        self._allocations[request_id] = descriptor
        return descriptor

    def read_allocation(self, request_id: str) -> HandoffDescriptor | None:
        if request_id in self._allocations:
            return self._allocations[request_id]
        def read(cur):
            cur.execute("SELECT w.allocation_id, t.task_key, w.repository_registration_id, w.worktree_path, w.task_branch, w.baseline_commit, w.allocation_idempotency_key, w.state FROM activity.git_workspaces AS w JOIN activity.tasks AS t ON t.id=w.task_id WHERE w.allocation_id=(SELECT allocation_id FROM activity.phase5b_execution_bindings WHERE execution_request_id=%s)", (request_id,))
            row = cur.fetchone()
            return (200, {"row": row}) if row else (404, {})
        result = self._transaction(read, read_only=True, missing_ok=True)
        if result is None:
            return None
        row = result["row"]
        descriptor = HandoffDescriptor(row[1], row[2], str(row[0]), str(row[0]), row[3], row[5], row[4], row[6], True, row[7])
        self._allocations[request_id] = descriptor
        return descriptor

    def store_work_order(self, request_id: str, order: dict) -> None:
        claim = self._claims[request_id]
        allocation = self._allocations[request_id]
        response = self._transaction(lambda cur: self.handler._phase5b_bind_execution(cur, request_id, claim["claim_id"], claim["run_id"], allocation.allocation_id, order))
        self._orders[request_id] = order
        if response.get("duplicate") and response.get("work_order_sha256") != hashlib.sha256(canonical_json(order)).hexdigest():
            raise RuntimeError("work-order replay conflict")

    def read_work_order(self, request_id: str) -> dict | None:
        result = self._transaction(lambda cur: self.handler._phase5b_read_execution(cur, request_id), read_only=True, missing_ok=True)
        if result is None:
            return None
        self._orders[request_id] = result["work_order"]
        return result["work_order"]

    def register_artifacts(self, custody: CustodyResult, claim: dict) -> dict:
        if custody.patch is None:
            raise RuntimeError("artifact_incomplete")
        def register(cur):
            responses = []
            for artifact in (custody.result, custody.patch):
                artifact_type = artifact.artifact_type
                artifact_id = str(uuid.uuid5(uuid.NAMESPACE_URL, artifact.artifact_id))
                filename = {PHASE5B_RESULT_ARTIFACT: "result.json", PHASE5B_PATCH_ARTIFACT: "patch.diff", PHASE5B_FAILURE_ARTIFACT: "failure.json"}[artifact_type]
                metadata = {"request_id": claim["request_id"], "run_id": claim["run_id"], "attempt_number": claim["attempt_number"], "artifact_type": artifact_type}
                descriptor = {"artifact_id": artifact_id, "artifact_type": artifact_type, "retained_path": str(PHASE5B_RETAINED_ROOT / claim["request_id"] / claim["run_id"] / str(claim["attempt_number"]) / filename), "sha256": artifact.sha256, "size_bytes": artifact.size_bytes, "media_type": "application/json" if artifact_type == PHASE5B_RESULT_ARTIFACT else "text/x-diff", "metadata": metadata}
                status, response = self.handler._phase5b_register_artifact(cur, claim["request_id"], claim["run_id"], claim["attempt_number"], f"{claim['request_id']}:{claim['run_id']}:{claim['attempt_number']}:{artifact_type}", descriptor)
                if status >= 400:
                    return status, response
                responses.append(response)
            return 200, {"result": responses[0], "patch": responses[1], "duplicate": all(item["duplicate"] for item in responses)}
        return self._transaction(register)

    def read_artifacts(self, claim: dict) -> CustodyResult | None:
        def read(cur):
            cur.execute("SELECT id, artifact_type, protected_absolute_path, sha256, size_bytes FROM activity.run_artifacts WHERE execution_request_id=%s AND run_id=%s AND idempotency_key LIKE %s ORDER BY artifact_type", (claim["request_id"], claim["run_id"], f"{claim['request_id']}:{claim['run_id']}:{claim['attempt_number']}:%"))
            return 200, {"rows": cur.fetchall()}
        rows = self._transaction(read, read_only=True)["rows"]
        records = {row[1]: RetainedArtifact(row[1], str(row[0]), row[2], row[3], row[4], True) for row in rows}
        if PHASE5B_RESULT_ARTIFACT not in records or PHASE5B_PATCH_ARTIFACT not in records:
            return None
        return CustodyResult(records[PHASE5B_RESULT_ARTIFACT], records[PHASE5B_PATCH_ARTIFACT], True)

    def register_failure_artifact(self, artifact: RetainedArtifact, claim: dict) -> dict:
        artifact_id = str(uuid.uuid5(uuid.NAMESPACE_URL, artifact.artifact_id))
        key = f"{claim['request_id']}:{claim['run_id']}:{claim['attempt_number']}:{PHASE5B_FAILURE_ARTIFACT}"
        descriptor = {"artifact_id": artifact_id, "artifact_type": PHASE5B_FAILURE_ARTIFACT, "retained_path": artifact.retained_path, "sha256": artifact.sha256, "size_bytes": artifact.size_bytes, "media_type": "application/json", "metadata": {"request_id": claim["request_id"], "claim_id": claim["claim_id"], "run_id": claim["run_id"], "attempt_number": claim["attempt_number"], "artifact_type": PHASE5B_FAILURE_ARTIFACT}}
        return self._transaction(lambda cur: self.handler._phase5b_register_artifact(cur, claim["request_id"], claim["run_id"], claim["attempt_number"], key, descriptor))

    def read_failure_artifact(self, claim: dict) -> RetainedArtifact | None:
        key = f"{claim['request_id']}:{claim['run_id']}:{claim['attempt_number']}:{PHASE5B_FAILURE_ARTIFACT}"
        def read(cur):
            cur.execute("SELECT id, artifact_type, protected_absolute_path, sha256, size_bytes FROM activity.run_artifacts WHERE execution_request_id=%s AND run_id=%s AND artifact_type=%s AND idempotency_key=%s", (claim["request_id"], claim["run_id"], PHASE5B_FAILURE_ARTIFACT, key))
            return 200, {"row": cur.fetchone()}
        row = self._transaction(read, read_only=True)["row"]
        return None if row is None else RetainedArtifact(row[1], str(row[0]), row[2], row[3], row[4], True)

    def finish(self, claim: dict) -> dict:
        body = self._claim_body(claim, f"{claim['request_id']}:attempt:{claim['attempt_number']}:finish")
        request_hash = self.handler._controller_request_hash("finish", body, token_hash(claim["claim_token"]))
        return self._transaction(lambda cur: self.handler._phase5b_finish(cur, claim["request_id"], body, request_hash))

    def read_cancellation(self, claim: dict) -> dict | None:
        def read(cur):
            intent = self.handler._phase5b_cancellation(cur, claim['request_id'])
            if intent and (intent.get('claim_id') != claim['claim_id'] or intent.get('run_id') != claim['run_id'] or intent.get('contract_sha256') != claim['contract_sha256']):
                return 409, {'error': 'cancellation binding mismatch'}
            return 200, {'intent': intent, 'state': self._request_state(cur, claim['request_id'])}
        result = self._transaction(read, read_only=True)
        return None if result['intent'] is None else {**result['intent'], 'closed': result['state'] == 'closed'}

    def complete_cancellation(self, claim: dict, owner: dict, proof) -> dict:
        from dataclasses import asdict
        body = {**self._claim_body(claim, f"{claim['request_id']}:attempt:{claim['attempt_number']}:cancel"),
                'owner': owner, 'stop_proof': asdict(proof)}
        return self._command('/v1/controller/complete-cancellation', body)

    def release_cancellation_writer(self, claim: dict, owner: dict) -> None:
        """Release/replay only the owner attested by this exact closed cancellation."""
        def release(cur):
            cur.execute("SELECT current_state FROM activity.execution_requests WHERE id=%s FOR UPDATE", (claim['request_id'],))
            state = cur.fetchone()
            cur.execute("SELECT metadata FROM activity.execution_request_events WHERE execution_request_id=%s AND idempotency_key='phase5b:cancellation:cancelled'", (claim['request_id'],))
            row = cur.fetchone()
            if (not state or state[0] != 'closed' or not row or row[0].get('owner') != owner
                    or row[0].get('intent', {}).get('claim_id') != claim['claim_id']
                    or row[0].get('intent', {}).get('run_id') != claim['run_id']
                    or row[0].get('claim_token_sha256') != token_hash(claim['claim_token'])):
                return 409, {'error': 'exact closed cancellation required'}
            cur.execute("SELECT state FROM activity.phase5b_execution_writer_leases WHERE allocation_id=%s AND writer_id=%s AND generation=%s AND fence_sha256=%s AND execution_request_id=%s AND controller_lease_id=%s AND run_id=%s FOR UPDATE", (owner['allocation_id'], owner['writer_id'], owner['generation'], owner['fence_sha256'], claim['request_id'], claim['claim_id'], claim['run_id']))
            writer = cur.fetchone()
            if not writer or writer[0] not in ('active', 'released'):
                return 409, {'error': 'writer identity/state ambiguous'}
            if writer[0] == 'active':
                cur.execute("UPDATE activity.phase5b_execution_writer_leases SET state='released', released_at=now() WHERE allocation_id=%s AND writer_id=%s AND generation=%s AND fence_sha256=%s", (owner['allocation_id'], owner['writer_id'], owner['generation'], owner['fence_sha256']))
            return 200, {'released': True, 'duplicate': writer[0] == 'released'}
        self._transaction(release)

    def fail(self, claim: dict, classification: str) -> dict:
        """Close a failed Phase 5B attempt through the authenticated controller command."""
        key = f"{claim['request_id']}:attempt:{claim['attempt_number']}:fail"
        body = {**self._claim_body(claim, key), "failure_classification": classification}
        return self._command("/v1/controller/fail", body)

    def read_claim(self, request_id: str) -> dict | None:
        # Poll durable authority every time. Cached claim responses omit lease_valid
        # and must never hide expiry, release, replacement or revoked authority.
        def read(cur):
            cur.execute("SELECT l.id, l.attempt_number, l.controller_id, r.contract_sha256, run.id, r.current_state, l.lease_expires_at, (l.state='active' AND l.lease_expires_at > now()) FROM activity.execution_controller_leases AS l JOIN activity.execution_requests AS r ON r.id=l.execution_request_id LEFT JOIN activity.runs AS run ON run.execution_request_id=r.id WHERE l.execution_request_id=%s ORDER BY l.attempt_number DESC LIMIT 1", (request_id,))
            row = cur.fetchone()
            return (200, {"row": row}) if row else (404, {})
        result = self._transaction(read, read_only=True, missing_ok=True)
        if result is None:
            return None
        row = result["row"]
        claim = {"request_id": request_id, "claim_id": str(row[0]), "attempt_number": row[1], "controller_id": row[2], "contract_sha256": row[3], "run_id": str(row[4]) if row[4] is not None else None, "state": row[5], "lease_valid": row[7] is True}
        previous = self._claims.get(request_id)
        if previous and any(previous.get(key) != claim[key] for key in ('claim_id', 'controller_id', 'contract_sha256', 'attempt_number')):
            # A cached ownership replacement is not fresh-controller recovery.
            # Keep the original cache so repeated reads cannot derive authority.
            return claim
        if previous and all(previous.get(key) == claim[key] for key in ('claim_id', 'controller_id', 'contract_sha256', 'attempt_number')):
            if 'claim_token' in previous:
                claim['claim_token'] = previous['claim_token']
        if 'claim_token' not in claim and self.claim_token_secret is not None and claim['controller_id'] == self.controller_id:
            material = f"phase5b:{request_id}:{self.controller_id}:{claim['attempt_number']}".encode()
            claim['claim_token'] = base64.urlsafe_b64encode(hmac.new(self.claim_token_secret, material, hashlib.sha256).digest()).decode().rstrip('=')
        self._claims[request_id] = claim
        return claim

    def state(self, request_id: str) -> str | None:
        result = self._transaction(lambda cur: (200, {"state": self._request_state(cur, request_id)}), read_only=True)
        return result["state"]

    def read_admission(self, request_id: str) -> dict | None:
        """Read the persisted request; caller supplies no contract or authority overrides."""
        request_id = _uuid(request_id, "request_id")
        def read(cur):
            cur.execute("SELECT normalized_contract, contract_sha256, current_state, workflow_template, executor_profile FROM activity.execution_requests WHERE id=%s", (request_id,))
            row = cur.fetchone()
            return (200, {'row': row}) if row else (404, {})
        result = self._transaction(read, read_only=True, missing_ok=True)
        if result is None:
            return None
        row = result['row']
        return {'request_id': request_id, 'normalized_contract': row[0],
                'contract_sha256': row[1], 'state': row[2],
                'workflow_template': row[3], 'executor_profile': row[4]}

    @staticmethod
    def _request_state(cur, request_id: str):
        cur.execute("SELECT current_state FROM activity.execution_requests WHERE id=%s", (request_id,))
        row = cur.fetchone()
        return row[0] if row else None


class PostgresPhase5BWriter:
    """Controller writer seam backed by migration-011 fencing rows."""

    def __init__(self, connection_factory: Callable[[], object], *, handler: Handler | None = None, require_runtime_enforcement: bool = True, enforcement_available: bool = False) -> None:
        self.connection_factory = connection_factory
        self.handler = handler or object.__new__(Handler)
        self.require_runtime_enforcement = require_runtime_enforcement
        self.enforcement_available = enforcement_available

    def _tx(self, operation: Callable[[object], tuple[int, dict]]) -> dict:
        db = self.connection_factory()
        cur = None
        try:
            cur = db.cursor(); status, response = operation(cur)
            if status >= 400:
                db.rollback(); raise RuntimeError(response.get("error", "writer operation failed"))
            db.commit(); return response
        finally:
            try:
                if cur is not None:
                    cur.close()
            finally: db.close()

    def acquire(self, allocation: Any, claim: dict) -> dict:
        if self.require_runtime_enforcement and not self.enforcement_available:
            raise RuntimeError("writer_enforcement_unavailable")
        descriptor = allocation.as_dict() if hasattr(allocation, "as_dict") else dict(allocation)
        fence = hashlib.sha256(f"{claim['request_id']}:{claim['run_id']}:{descriptor['allocation_id']}:{claim['attempt_number']}".encode()).hexdigest()
        return self._tx(lambda cur: self.handler._phase5b_writer_acquire(cur, claim["request_id"], claim["claim_id"], claim["run_id"], descriptor["allocation_id"], descriptor["worktree_id"], claim["controller_id"], claim["attempt_number"], fence, 30))

    def valid(self, owner: dict) -> bool:
        db = self.connection_factory()
        cur = None
        try:
            cur = db.cursor(); cur.execute("SELECT 1 FROM activity.phase5b_execution_writer_leases WHERE allocation_id=%s AND writer_id=%s AND generation=%s AND fence_sha256=%s AND state='active' AND lease_expires_at > now()", (owner["allocation_id"], owner.get("writer_id"), owner["generation"], owner["fence_sha256"]))
            return cur.fetchone() is not None
        finally:
            try:
                if cur is not None:
                    cur.close()
            finally: db.close()

    def release(self, owner: dict) -> None:
        self._tx(lambda cur: self.handler._phase5b_writer_release(cur, owner["allocation_id"], owner["writer_id"], owner["generation"], owner["fence_sha256"]))


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
