from __future__ import annotations

import base64
import binascii
import json
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
MISLEADING_SEARCH_QUERIES = {"*", "**", ".*", "^", "$"}
CURSOR_VERSION = 1


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


def _baseline_root() -> Path:
    root = get_settings().notes_baseline_root
    if root is None:
        raise NotesRepositoryError("JARVIS_NOTES_BASELINE is not configured.", "NOT_CONFIGURED")
    return root.resolve()


def _directory_path(directory: str | None) -> Path:
    return _baseline_root() if not directory else resolve_baseline_path(directory, markdown_only=False)


def _is_visible_within_root(path: Path) -> bool:
    root = _baseline_root()
    try:
        relative = path.relative_to(root)
        path.resolve().relative_to(root)
    except ValueError:
        return False
    return not any(part.startswith(".") for part in relative.parts)


def _markdown_files(directory: str | None = None, *, recursive: bool = True) -> list[Path]:
    start = _directory_path(directory)
    if not start.exists() or not start.is_dir():
        return []
    candidates = start.rglob("*.md") if recursive else start.glob("*.md")
    files = [path.resolve() for path in candidates if path.is_file() and _is_visible_within_root(path)]
    return sorted(files, key=lambda item: _relative(item).casefold())


def _relative(path: Path) -> str:
    return path.relative_to(_baseline_root()).as_posix()


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


def _matches_filters(frontmatter: dict[str, Any], filters: dict[str, Any] | None) -> bool:
    return not filters or all(frontmatter.get(key) == value for key, value in filters.items())


def _cursor_context(
    operation: str,
    commit: str | None,
    *,
    directory: str | None,
    filters: dict[str, Any] | None,
    recursive: bool,
    query: str | None = None,
    match_mode: str | None = None,
    case_sensitive: bool | None = None,
) -> dict[str, Any]:
    return {
        "version": CURSOR_VERSION,
        "operation": operation,
        "commit": commit,
        "directory": directory or "",
        "filters": filters or {},
        "recursive": recursive,
        "query": query,
        "match_mode": match_mode,
        "case_sensitive": case_sensitive,
    }


def _encode_cursor(context: dict[str, Any], offset: int) -> str:
    payload = {**context, "offset": offset}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str, expected: dict[str, Any]) -> tuple[int, str | None]:
    try:
        padding = "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(cursor + padding))
    except (ValueError, TypeError, json.JSONDecodeError, binascii.Error) as exc:
        raise NotesRepositoryError("The pagination cursor is invalid.", "INVALID_CURSOR") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("offset"), int) or payload["offset"] < 0:
        raise NotesRepositoryError("The pagination cursor is invalid.", "INVALID_CURSOR")
    cursor_commit = payload.get("commit")
    if cursor_commit != expected.get("commit"):
        return payload["offset"], str(cursor_commit) if cursor_commit is not None else None
    comparable = dict(payload)
    comparable.pop("offset", None)
    if comparable != expected:
        raise NotesRepositoryError("The cursor does not match this request.", "CURSOR_REQUEST_MISMATCH")
    return payload["offset"], cursor_commit


def _page_offset(cursor: str | None, context: dict[str, Any], operation: str) -> int | NotesResult:
    if not cursor:
        return 0
    offset, cursor_commit = _decode_cursor(cursor, context)
    if cursor_commit != context.get("commit"):
        return NotesResult(
            "conflict",
            operation,
            context.get("commit"),
            error_code="BASELINE_CHANGED",
            message="The approved baseline changed during pagination. Restart from the first page.",
            data={"cursor_commit": cursor_commit, "current_commit": context.get("commit")},
        )
    return offset


def _note_summary(note_path: Path, frontmatter: dict[str, Any] | None = None) -> dict[str, Any]:
    if frontmatter is None:
        content, _ = _read_bounded(note_path)
        frontmatter, _body = parse_frontmatter(content)
    return {
        "path": _relative(note_path),
        "title": frontmatter.get("title") or note_path.stem,
        "size": note_path.stat().st_size,
        "frontmatter": frontmatter,
    }


def _validate_operation_arguments(
    operation: str,
    *,
    path: str | None,
    directory: str | None,
    query: str | None,
    cursor: str | None,
    match_mode: str,
    filters: dict[str, Any] | None,
    recursive: bool,
    case_sensitive: bool,
    max_depth: int,
    max_matches_per_note: int,
) -> None:
    path_operations = {"read", "metadata", "headings", "outgoing_links", "backlinks"}
    directory_operations = {"browse", "inventory", "list", "search", "backlinks", "resolve_link"}
    query_operations = {"search", "resolve_link"}
    cursor_operations = {"list", "search"}
    if path is not None and operation not in path_operations:
        raise NotesRepositoryError(f"{operation} does not accept path.", "INVALID_INPUT")
    if directory is not None and operation not in directory_operations:
        raise NotesRepositoryError(f"{operation} does not accept directory.", "INVALID_INPUT")
    if query is not None and operation not in query_operations:
        raise NotesRepositoryError(f"{operation} does not accept query.", "INVALID_INPUT")
    if cursor is not None and operation not in cursor_operations:
        raise NotesRepositoryError(f"{operation} does not accept cursor.", "INVALID_INPUT")
    if operation != "search" and match_mode != "literal":
        raise NotesRepositoryError(f"{operation} does not accept match_mode.", "INVALID_INPUT")
    if filters is not None and operation not in {"list", "search"}:
        raise NotesRepositoryError(f"{operation} does not accept filters.", "INVALID_INPUT")
    if recursive is False and operation not in {"list", "search"}:
        raise NotesRepositoryError(f"{operation} does not accept recursive.", "INVALID_INPUT")
    if case_sensitive and operation != "search":
        raise NotesRepositoryError(f"{operation} does not accept case_sensitive.", "INVALID_INPUT")
    if max_depth != 4 and operation != "inventory":
        raise NotesRepositoryError(f"{operation} does not accept max_depth.", "INVALID_INPUT")
    if max_matches_per_note != 5 and operation != "search":
        raise NotesRepositoryError(f"{operation} does not accept max_matches_per_note.", "INVALID_INPUT")


def notes_read(
    operation: str,
    *,
    path: str | None = None,
    directory: str | None = None,
    query: str | None = None,
    filters: dict[str, Any] | None = None,
    limit: int = 25,
    cursor: str | None = None,
    recursive: bool = True,
    match_mode: str = "literal",
    case_sensitive: bool = False,
    max_depth: int = 4,
    max_matches_per_note: int = 5,
) -> NotesResult:
    settings = get_settings()
    limit = max(1, min(limit, settings.notes_max_results))
    max_depth = max(0, min(max_depth, 20))
    max_matches_per_note = max(1, min(max_matches_per_note, 20))
    commit = _safe_commit()
    try:
        _validate_operation_arguments(
            operation,
            path=path,
            directory=directory,
            query=query,
            cursor=cursor,
            match_mode=match_mode,
            filters=filters,
            recursive=recursive,
            case_sensitive=case_sensitive,
            max_depth=max_depth,
            max_matches_per_note=max_matches_per_note,
        )

        if operation == "browse":
            start = _directory_path(directory)
            if not start.exists() or not start.is_dir():
                return NotesResult("not_found", operation, commit, error_code="NOT_FOUND", message="Directory not found.")
            directories = sorted(
                (_relative(item.resolve()) for item in start.iterdir() if item.is_dir() and _is_visible_within_root(item)),
                key=str.casefold,
            )
            notes = [_note_summary(item) for item in _markdown_files(directory, recursive=False)]
            return NotesResult(
                "success",
                operation,
                commit,
                data={
                    "directory": directory or "",
                    "directories": directories,
                    "notes": notes,
                    "directory_count": len(directories),
                    "note_count": len(notes),
                    "complete": True,
                },
            )

        if operation == "inventory":
            start = _directory_path(directory)
            if not start.exists() or not start.is_dir():
                return NotesResult("not_found", operation, commit, error_code="NOT_FOUND", message="Directory not found.")
            all_notes = _markdown_files(directory, recursive=True)
            start_depth = len(start.relative_to(_baseline_root()).parts)
            tree = []
            omitted_by_depth = False
            visible_directories = [
                item for item in start.rglob("*") if item.is_dir() and _is_visible_within_root(item)
            ]
            for candidate in sorted(visible_directories, key=lambda item: _relative(item.resolve()).casefold()):
                depth = len(candidate.relative_to(_baseline_root()).parts) - start_depth
                if depth > max_depth:
                    omitted_by_depth = True
                    continue
                count = sum(1 for note in all_notes if candidate.resolve() in note.parents)
                tree.append({"path": _relative(candidate.resolve()), "type": "directory", "note_count_recursive": count})
            return NotesResult(
                "success",
                operation,
                commit,
                data={
                    "directory": directory or "",
                    "tree": tree,
                    "total_notes": len(all_notes),
                    "max_depth": max_depth,
                    "tree_truncated_by_depth": omitted_by_depth,
                    "note_total_complete": True,
                    "tree_complete": not omitted_by_depth,
                    "complete": not omitted_by_depth,
                },
            )

        if operation == "list":
            candidates = []
            for note_path in _markdown_files(directory, recursive=recursive):
                content, _ = _read_bounded(note_path)
                frontmatter, _body = parse_frontmatter(content)
                if _matches_filters(frontmatter, filters):
                    candidates.append(_note_summary(note_path, frontmatter))
            context = _cursor_context(operation, commit, directory=directory, filters=filters, recursive=recursive)
            offset = _page_offset(cursor, context, operation)
            if isinstance(offset, NotesResult):
                return offset
            page = candidates[offset : offset + limit]
            next_offset = offset + len(page)
            has_more = next_offset < len(candidates)
            return NotesResult(
                "success",
                operation,
                commit,
                data={
                    "notes": page,
                    "count": len(page),
                    "returned_count": len(page),
                    "total_count": len(candidates),
                    "limit": limit,
                    "recursive": recursive,
                    "has_more": has_more,
                    "next_cursor": _encode_cursor(context, next_offset) if has_more else None,
                    "complete": not has_more,
                },
            )

        if operation in {"read", "metadata", "headings", "outgoing_links"}:
            if not path:
                raise NotesRepositoryError("This operation requires path.", "INVALID_INPUT")
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
                "complete": not truncated,
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
                raise NotesRepositoryError("Search requires a non-empty query.", "INVALID_QUERY")
            if query.strip() in MISLEADING_SEARCH_QUERIES:
                raise NotesRepositoryError(
                    "Search performs literal text matching and does not support wildcards or regular expressions. "
                    "Use browse or list to discover notes.",
                    "WILDCARD_NOT_SUPPORTED",
                )
            if match_mode != "literal":
                raise NotesRepositoryError("Only literal search is currently supported.", "MATCH_MODE_NOT_SUPPORTED")
            needle = query if case_sensitive else query.casefold()
            matched_notes = []
            total_match_count = 0
            content_scan_truncated = False
            for note_path in _markdown_files(directory, recursive=recursive):
                content, content_truncated = _read_bounded(note_path)
                content_scan_truncated = content_scan_truncated or content_truncated
                frontmatter, _body = parse_frontmatter(content)
                if not _matches_filters(frontmatter, filters):
                    continue
                matches = []
                note_match_count = 0
                for line_number, line in enumerate(content.splitlines(), start=1):
                    haystack = line if case_sensitive else line.casefold()
                    if needle in haystack:
                        note_match_count += 1
                        if len(matches) < max_matches_per_note:
                            matches.append({"line": line_number, "excerpt": line[:500]})
                if note_match_count:
                    total_match_count += note_match_count
                    matched_notes.append(
                        {
                            "path": _relative(note_path),
                            "match_count": note_match_count,
                            "matches": matches,
                            "matches_truncated": note_match_count > len(matches),
                            "content_truncated": content_truncated,
                        }
                    )
            context = _cursor_context(
                operation,
                commit,
                directory=directory,
                filters=filters,
                recursive=recursive,
                query=query,
                match_mode=match_mode,
                case_sensitive=case_sensitive,
            )
            offset = _page_offset(cursor, context, operation)
            if isinstance(offset, NotesResult):
                return offset
            page = matched_notes[offset : offset + limit]
            next_offset = offset + len(page)
            has_more = next_offset < len(matched_notes)
            returned_matches = sum(item["match_count"] for item in page)
            return NotesResult(
                "success",
                operation,
                commit,
                data={
                    "query": query,
                    "match_mode": match_mode,
                    "case_sensitive": case_sensitive,
                    "notes": page,
                    "returned_note_count": len(page),
                    "total_note_count": len(matched_notes),
                    "returned_match_count": returned_matches,
                    "total_match_count": total_match_count,
                    "content_scan_truncated": content_scan_truncated,
                    "has_more": has_more,
                    "next_cursor": _encode_cursor(context, next_offset) if has_more else None,
                    "complete": not has_more and not content_scan_truncated,
                },
            )

        if operation == "backlinks":
            if not path:
                raise NotesRepositoryError("Backlinks requires path.", "INVALID_INPUT")
            target = Path(path).with_suffix("").as_posix()
            target_name = Path(target).name
            matches = []
            for note_path in _markdown_files(directory, recursive=True):
                content, _ = _read_bounded(note_path)
                outgoing = _links(content)
                if any(link.removesuffix(".md") in {target, target_name} for link in outgoing):
                    matches.append({"path": _relative(note_path)})
                    if len(matches) >= limit:
                        break
            return NotesResult("success", operation, commit, path=path, data={"backlinks": matches, "count": len(matches)})

        if operation == "resolve_link":
            if not query or not query.strip():
                raise NotesRepositoryError("resolve_link requires query.", "INVALID_QUERY")
            target = query.split("|", 1)[0].split("#", 1)[0].removesuffix(".md")
            candidates = [
                _relative(note_path)
                for note_path in _markdown_files(directory, recursive=True)
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
