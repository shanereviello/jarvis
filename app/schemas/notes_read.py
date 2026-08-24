from __future__ import annotations

from typing import Literal


NotesReadOperation = Literal[
    "browse",
    "inventory",
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

NotesSearchMatchMode = Literal["literal"]
