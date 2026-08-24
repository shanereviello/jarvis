from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from app.services.notes import read_note


def register(server: FastMCP) -> None:
    @server.tool(
        name="read-note",
        description="Backward-compatible wrapper that reads one Markdown note from the approved Git baseline.",
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    def read_note_tool(notes_path: str) -> dict:
        return read_note(notes_path).to_dict()
