from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from app.schemas.notes_write import NotesWriteOperation
from app.services.notes_writer import notes_write


def register(server: FastMCP) -> None:
    @server.tool(
        name="notes-write",
        description=(
            "Create or modify an attributed Jarvis draft in the review worktree. Writes are restricted to "
            "Jarvis Drafts and Jarvis Second Brain. This tool never stages, commits, pushes, or merges Git changes. "
            "Operations: create, replace_draft, append, update_section."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=False,
        ),
    )
    def notes_write_tool(
        operation: NotesWriteOperation,
        path: str,
        title: str | None = None,
        content: str | None = None,
        heading: str | None = None,
        expected_hash: str | None = None,
        sources: list[str] | None = None,
        generation_run: str | None = None,
    ) -> dict[str, Any]:
        return notes_write(
            operation,
            path=path,
            title=title,
            content=content,
            heading=heading,
            expected_hash=expected_hash,
            sources=sources,
            generation_run=generation_run,
        ).to_dict()
