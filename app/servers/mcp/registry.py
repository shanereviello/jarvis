from mcp.server.fastmcp import FastMCP

from app.prompts import register_engineering_db_query_planner_prompt
from app.resources import register_engineering_db_schema_resources
from app.tools import (
    register_engineering_db_connection_lookup_tool,
    register_engineering_db_lookup_tool,
    register_read_note_tool,
    register_notes_read_tool,
    register_notes_write_tool,
    register_retrieve_engineering_db_schema_context_tool,
)


def register_tools(server: FastMCP) -> None:
    register_retrieve_engineering_db_schema_context_tool(server)
    register_engineering_db_lookup_tool(server)
    register_engineering_db_connection_lookup_tool(server)
    register_read_note_tool(server)
    register_notes_read_tool(server)
    register_notes_write_tool(server)
    register_engineering_db_schema_resources(server)
    register_engineering_db_query_planner_prompt(server)
