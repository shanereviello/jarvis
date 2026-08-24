from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


NoteStatus = Literal[
    "success",
    "partial_success",
    "not_found",
    "conflict",
    "refused",
    "failed",
]


@dataclass(slots=True)
class NotesResult:
    status: NoteStatus
    operation: str
    baseline_commit: str | None = None
    path: str | None = None
    changed: bool = False
    data: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    message: str | None = None

    @property
    def ok(self) -> bool:
        return self.status in {"success", "partial_success"}

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["ok"] = self.ok
        return payload
