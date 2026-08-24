from __future__ import annotations

import hashlib
import os
import re
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from app.core.config import get_settings


PROTECTED_PARTS = {".git", ".obsidian", ".trash", ".env"}
FRONTMATTER_PATTERN = re.compile(r"\A---\s*\n(.*?)\n---\s*(?:\n|\Z)", re.DOTALL)


class NotesRepositoryError(ValueError):
    def __init__(self, message: str, error_code: str = "INVALID_PATH") -> None:
        super().__init__(message)
        self.error_code = error_code


def _configured_root(kind: str) -> Path:
    settings = get_settings()
    root = (
        settings.notes_baseline_root
        if kind == "baseline"
        else settings.notes_review_root
    )
    if root is None:
        env_name = "JARVIS_NOTES_BASELINE" if kind == "baseline" else "JARVIS_NOTES_REVIEW"
        raise NotesRepositoryError(f"{env_name} is not configured.", "NOT_CONFIGURED")
    return root.resolve()


def _validate_relative_path(relative_path: str, *, markdown_only: bool = True) -> PurePosixPath:
    if not relative_path or not relative_path.strip():
        raise NotesRepositoryError("A non-empty vault-relative path is required.")
    if "\\" in relative_path:
        raise NotesRepositoryError("Vault paths must use forward slashes.")
    path = PurePosixPath(relative_path)
    if path.is_absolute() or ".." in path.parts:
        raise NotesRepositoryError("Absolute paths and parent traversal are not allowed.")
    if any(part.startswith(".") or part.casefold() in PROTECTED_PARTS for part in path.parts):
        raise NotesRepositoryError("The requested path contains a protected component.", "PROTECTED_PATH")
    if markdown_only and path.suffix.casefold() != ".md":
        raise NotesRepositoryError("Only Markdown (.md) files are allowed.", "NOT_MARKDOWN")
    return path


def _resolve(kind: str, relative_path: str, *, markdown_only: bool = True) -> Path:
    root = _configured_root(kind)
    relative = _validate_relative_path(relative_path, markdown_only=markdown_only)
    candidate = root.joinpath(*relative.parts)

    # Resolve the closest existing ancestor so a symlink cannot redirect a new file.
    ancestor = candidate
    missing: list[str] = []
    while not ancestor.exists() and ancestor != root:
        missing.append(ancestor.name)
        ancestor = ancestor.parent
    resolved = ancestor.resolve()
    for part in reversed(missing):
        resolved /= part
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise NotesRepositoryError("The requested path escapes the configured notes root.", "OUTSIDE_ALLOWED_ROOT") from exc
    return resolved


def resolve_baseline_path(relative_path: str, *, markdown_only: bool = True) -> Path:
    return _resolve("baseline", relative_path, markdown_only=markdown_only)


def resolve_review_path(relative_path: str, *, markdown_only: bool = True) -> Path:
    path = _resolve("review", relative_path, markdown_only=markdown_only)
    settings = get_settings()
    relative = path.relative_to(_configured_root("review"))
    allowed = {settings.notes_draft_root, settings.notes_second_brain_root}
    if not relative.parts or relative.parts[0] not in allowed:
        raise NotesRepositoryError(
            f"Writes are limited to {sorted(allowed)}.",
            "OUTSIDE_ALLOWED_ROOT",
        )
    return path


def calculate_sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def get_baseline_commit() -> str | None:
    root = _configured_root("baseline")
    try:
        git_marker = root / ".git"
        if git_marker.is_file():
            marker = git_marker.read_text(encoding="utf-8").strip()
            if not marker.startswith("gitdir: "):
                return None
            git_dir = Path(marker.removeprefix("gitdir: "))
            if not git_dir.is_absolute():
                git_dir = (root / git_dir).resolve()
        elif git_marker.is_dir():
            git_dir = git_marker
        else:
            return None
        head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
        if not head.startswith("ref: "):
            return head or None
        ref = head.removeprefix("ref: ")
        ref_path = git_dir / ref
        if ref_path.is_file():
            return ref_path.read_text(encoding="utf-8").strip() or None
        common_dir_file = git_dir / "commondir"
        if common_dir_file.is_file():
            common_dir = (git_dir / common_dir_file.read_text(encoding="utf-8").strip()).resolve()
            common_ref = common_dir / ref
            if common_ref.is_file():
                return common_ref.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None
    return None


def parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    match = FRONTMATTER_PATTERN.match(content)
    if not match:
        return {}, content
    try:
        parsed = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        raise NotesRepositoryError(f"Invalid YAML frontmatter: {exc}", "INVALID_FRONTMATTER") from exc
    if not isinstance(parsed, dict):
        raise NotesRepositoryError("YAML frontmatter must be a mapping.", "INVALID_FRONTMATTER")
    return parsed, content[match.end():]


def render_note(frontmatter: dict[str, Any], body: str) -> str:
    yaml_text = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True).strip()
    return f"---\n{yaml_text}\n---\n\n{body.rstrip()}\n"


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
