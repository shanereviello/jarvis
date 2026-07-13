from __future__ import annotations

from pathlib import Path

from app.core.config import get_settings
from app.schemas.notes import NoteReadResult


def _resolve_vault_path(notes_path: str) -> Path:
    settings = get_settings()
    if settings.vault_root is None:
        raise ValueError("JARVIS_VAULT_ROOT is not configured.")

    vault_root = settings.vault_root.resolve()
    candidate = (vault_root / notes_path).resolve()

    try:
        candidate.relative_to(vault_root)
    except ValueError as exc:
        raise ValueError("Requested note path escapes the configured vault root.") from exc

    return candidate


def read_note(notes_path: str) -> NoteReadResult:
    try:
        path = _resolve_vault_path(notes_path)
    except ValueError as exc:
        return NoteReadResult(
            ok=False,
            notes_path=notes_path,
            content="",
            error=str(exc),
        )

    if not path.exists() or not path.is_file():
        return NoteReadResult(
            ok=False,
            notes_path=notes_path,
            content="",
            error="Note file not found.",
        )

    content = path.read_text(encoding="utf-8", errors="ignore")[:8000]
    return NoteReadResult(
        ok=True,
        notes_path=notes_path,
        content=content,
    )
