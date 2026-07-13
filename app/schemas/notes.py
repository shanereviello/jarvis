from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(slots=True)
class NoteReadResult:
    ok: bool
    notes_path: str
    content: str
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)
