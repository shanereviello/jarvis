from __future__ import annotations

from app.schemas.notes import NoteReadResult
from app.services.notes_reader import notes_read


def read_note(notes_path: str) -> NoteReadResult:
    result = notes_read("read", path=notes_path)
    if not result.ok:
        return NoteReadResult(
            ok=False,
            notes_path=notes_path,
            content="",
            error=result.message,
        )
    return NoteReadResult(
        ok=True,
        notes_path=notes_path,
        content=str(result.data.get("content", "")),
    )
