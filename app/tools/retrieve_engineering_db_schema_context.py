from mcp.server.fastmcp import FastMCP

from app.services.engineering_db import retrieve_engineering_db_schema_context


def register(server: FastMCP) -> None:
    @server.tool(
        name="retrieve-engineering-db-schema-context",
        description=(
            "Inspect the engineering DB schema and suggest the most relevant tables, searchable "
            "columns, and relationships for a user query before running a DB lookup."
        ),
    )
    def retrieve_engineering_db_schema_context_tool(query: str, max_tables: int = 5) -> dict:
        return retrieve_engineering_db_schema_context(query, max_tables=max_tables).to_dict()
