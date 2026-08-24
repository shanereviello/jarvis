from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from app.schemas.notes_read import NotesReadOperation, NotesSearchMatchMode
from app.services.notes_reader import notes_read


def register(server: FastMCP) -> None:
    @server.tool(
        name="notes-read",
        description=(
            "Access Markdown notes in the approved Git baseline; pending review files are never read. "
            "Use browse to discover directories, inventory to summarize the vault tree, and list to enumerate notes. "
            "Use search only for literal text inside notes: wildcard, glob, and regex syntax are not supported. "
            "For list and search, follow next_cursor until has_more is false before claiming completeness. "
            "Operations: browse, inventory, list, read, search, metadata, headings, backlinks, outgoing_links, "
            "recent, resolve_link."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    def notes_read_tool(
        operation: NotesReadOperation,
        path: str | None = None,
        directory: str | None = None,
        query: str | None = None,
        filters: dict[str, Any] | None = None,
        limit: int = 25,
        cursor: str | None = None,
        recursive: bool = True,
        match_mode: NotesSearchMatchMode = "literal",
        case_sensitive: bool = False,
        max_depth: int = 4,
        max_matches_per_note: int = 5,
    ) -> dict[str, Any]:
        return notes_read(
            operation,
            path=path,
            directory=directory,
            query=query,
            filters=filters,
            limit=limit,
            cursor=cursor,
            recursive=recursive,
            match_mode=match_mode,
            case_sensitive=case_sensitive,
            max_depth=max_depth,
            max_matches_per_note=max_matches_per_note,
        ).to_dict()
