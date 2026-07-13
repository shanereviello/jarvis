from mcp.server.fastmcp import FastMCP

from app.services.notes import read_note


def register(server: FastMCP) -> None:
    @server.tool(
        name="read-note",
        description="Read a note file from the configured Jarvis vault root.",
    )
    def read_note_tool(notes_path: str) -> dict:
        return read_note(notes_path).to_dict()
