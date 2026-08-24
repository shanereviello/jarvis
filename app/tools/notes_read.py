from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from app.schemas.notes_read import NotesReadOperation
from app.services.notes_reader import notes_read


def register(server: FastMCP) -> None:
    @server.tool(
        name="notes-read",
        description=(
            "Read, list, search, inspect links, or inspect metadata for Markdown notes in the approved Git baseline. "
            "This tool never reads pending files from the Jarvis review worktree. Operations: list, read, search, "
            "metadata, headings, backlinks, outgoing_links, recent, resolve_link."
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
    ) -> dict[str, Any]:
        return notes_read(
            operation,
            path=path,
            directory=directory,
            query=query,
            filters=filters,
            limit=limit,
        ).to_dict()
