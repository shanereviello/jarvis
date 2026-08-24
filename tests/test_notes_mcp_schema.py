from __future__ import annotations

import anyio

from app.servers.mcp.server import create_server


def test_notes_read_schema_and_guidance_are_explicit() -> None:
    async def inspect() -> None:
        tools = {tool.name: tool for tool in await create_server().list_tools()}
        note_tool = tools["notes-read"]
        operations = note_tool.inputSchema["properties"]["operation"]["enum"]
        assert operations == [
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
        assert note_tool.inputSchema["properties"]["match_mode"]["const"] == "literal"
        assert "Use browse to discover directories" in note_tool.description
        assert "wildcard, glob, and regex syntax are not supported" in note_tool.description
        assert "follow next_cursor until has_more is false" in note_tool.description

    anyio.run(inspect)
