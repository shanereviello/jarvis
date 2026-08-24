from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.schemas.notes_common import NotesResult
from app.services.notes_repository import (
    NotesRepositoryError,
    calculate_sha256,
    get_baseline_commit,
    parse_frontmatter,
    resolve_baseline_path,
)


HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
WIKI_LINK_PATTERN = re.compile(r"!?\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")
MARKDOWN_LINK_PATTERN = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+\.md(?:#[^)]*)?)\)", re.IGNORECASE)


def _failure(operation: str, exc: Exception, path: str | None = None) -> NotesResult:
    code = exc.error_code if isinstance(exc, NotesRepositoryError) else "FAILED"
    return NotesResult(
        status="refused" if isinstance(exc, NotesRepositoryError) else "failed",
        operation=operation,
        baseline_commit=_safe_commit(),
        path=path,
        error_code=code,
        message=str(exc),
    )


def _safe_commit() -> str | None:
    try:
        return get_baseline_commit()
    except NotesRepositoryError:
        return None


def _markdown_files(directory: str | None = None) -> list[Path]:
    settings = get_settings()
    root = settings.notes_baseline_root
    if root is None:
        raise NotesRepositoryError("JARVIS_NOTES_BASELINE is not configured.", "NOT_CONFIGURED")
    root = root.resolve()
    start = root if not directory else resolve_baseline_path(directory, markdown_only=False)
    if not start.exists() or not start.is_dir():
        return []
    files: list[Path] = []
    for path in start.rglob("*.md"):
        relative = path.relative_to(root)
        if any(part.startswith(".") for part in relative.parts):
            continue
        try:
            resolved = path.resolve()
            resolved.relative_to(root)
        except ValueError:
            continue
        if resolved.is_file():
            files.append(resolved)
    return sorted(files, key=lambda item: item.relative_to(root).as_posix().casefold())


def _relative(path: Path) -> str:
    root = get_settings().notes_baseline_root
    assert root is not None
    return path.relative_to(root.resolve()).as_posix()


def _read_bounded(path: Path) -> tuple[str, bool]:
    maximum = get_settings().notes_max_content_bytes
    raw = path.read_bytes()
    truncated = len(raw) > maximum
    return raw[:maximum].decode("utf-8", errors="replace"), truncated


def _headings(content: str) -> list[dict[str, Any]]:
    return [
        {"level": len(match.group(1)), "heading": match.group(2), "line": content[: match.start()].count("\n") + 1}
        for match in HEADING_PATTERN.finditer(content)
    ]


def _links(content: str) -> list[str]:
    links = [match.group(1).strip() for match in WIKI_LINK_PATTERN.finditer(content)]
    links.extend(match.group(1).split("#", 1)[0].strip() for match in MARKDOWN_LINK_PATTERN.finditer(content))
    return list(dict.fromkeys(link for link in links if link))


def notes_read(
    operation: str,
    *,
    path: str | None = None,
    directory: str | None = None,
    query: str | None = None,
    filters: dict[str, Any] | None = None,
    limit: int = 25,
) -> NotesResult:
    settings = get_settings()
    limit = max(1, min(limit, settings.notes_max_results))
    commit = _safe_commit()
    try:
        if operation == "list":
            items = []
            for note_path in _markdown_files(directory):
                content, _ = _read_bounded(note_path)
                frontmatter, _body = parse_frontmatter(content)
                if filters and any(frontmatter.get(key) != value for key, value in filters.items()):
                    continue
                stat = note_path.stat()
                items.append(
                    {
                        "path": _relative(note_path),
                        "title": frontmatter.get("title") or note_path.stem,
                        "size": stat.st_size,
                        "frontmatter": frontmatter,
                    }
                )
                if len(items) >= limit:
                    break
            return NotesResult("success", operation, commit, data={"notes": items, "count": len(items), "limit": limit})

        if operation in {"read", "metadata", "headings", "outgoing_links"}:
            if not path:
                raise NotesRepositoryError("This operation requires path.")
            note_path = resolve_baseline_path(path)
            if not note_path.is_file():
                return NotesResult("not_found", operation, commit, path=path, error_code="NOT_FOUND", message="Note not found.")
            content, truncated = _read_bounded(note_path)
            frontmatter, body = parse_frontmatter(content)
            base = {
                "frontmatter": frontmatter,
                "content_hash": calculate_sha256(note_path),
                "size": note_path.stat().st_size,
                "truncated": truncated,
            }
            if operation == "read":
                base.update({"body": body, "content": content, "headings": _headings(body)})
            elif operation == "headings":
                base["headings"] = _headings(body)
            elif operation == "outgoing_links":
                base["links"] = _links(body)
            return NotesResult("partial_success" if truncated else "success", operation, commit, path=path, data=base)

        if operation == "search":
            if not query or not query.strip():
                raise NotesRepositoryError("Search requires a non-empty query.")
            needle = query.casefold()
            matches = []
            for note_path in _markdown_files(directory):
                content, _ = _read_bounded(note_path)
                frontmatter, _body = parse_frontmatter(content)
                if filters and any(frontmatter.get(key) != value for key, value in filters.items()):
                    continue
                for line_number, line in enumerate(content.splitlines(), start=1):
                    if needle in line.casefold():
                        matches.append({"path": _relative(note_path), "line": line_number, "excerpt": line[:500]})
                        if len(matches) >= limit:
                            break
                if len(matches) >= limit:
                    break
            return NotesResult("success", operation, commit, data={"query": query, "matches": matches, "count": len(matches)})

        if operation == "backlinks":
            if not path:
                raise NotesRepositoryError("Backlinks requires path.")
            target = Path(path).with_suffix("").as_posix()
            target_name = Path(target).name
            matches = []
            for note_path in _markdown_files(directory):
                content, _ = _read_bounded(note_path)
                outgoing = _links(content)
                if any(link.removesuffix(".md") in {target, target_name} for link in outgoing):
                    matches.append({"path": _relative(note_path)})
                    if len(matches) >= limit:
                        break
            return NotesResult("success", operation, commit, path=path, data={"backlinks": matches, "count": len(matches)})

        if operation == "resolve_link":
            if not query or not query.strip():
                raise NotesRepositoryError("resolve_link requires query.")
            target = query.split("|", 1)[0].split("#", 1)[0].removesuffix(".md")
            candidates = [
                _relative(note_path)
                for note_path in _markdown_files(directory)
                if _relative(note_path).removesuffix(".md") == target or note_path.stem == Path(target).name
            ][:limit]
            status = "success" if len(candidates) <= 1 else "partial_success"
            return NotesResult(status, operation, commit, data={"query": query, "candidates": candidates, "ambiguous": len(candidates) > 1})

        if operation == "recent":
            root = settings.notes_baseline_root
            assert root is not None
            result = subprocess.run(
                [
                    "git",
                    "-c",
                    f"safe.directory={root}",
                    "-C",
                    str(root),
                    "log",
                    f"-{limit}",
                    "--name-only",
                    "--pretty=format:%H|%aI|%s",
                    "--",
                    "*.md",
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
            return NotesResult("success", operation, commit, data={"git_log": result.stdout, "limit": limit})

        raise NotesRepositoryError(f"Unsupported read operation: {operation}", "INVALID_OPERATION")
    except (NotesRepositoryError, OSError, subprocess.SubprocessError) as exc:
        return _failure(operation, exc, path)
