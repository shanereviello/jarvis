from __future__ import annotations

from typing import Literal


NotesReadOperation = Literal[
    "list",
    "read",
    "search",
    "metadata",
    "headings",
    "backlinks",
    "outgoing_links",
    "recent",
    "resolve_link",
]
