from mcp.server.fastmcp import FastMCP

from app.services.engineering_db import engineering_db_lookup


def register(server: FastMCP) -> None:
    @server.tool(
        name="engineering-db-lookup",
        description=(
            "Query the engineering DB for structured results. Prefer calling "
            "retrieve-engineering-db-schema-context first to narrow the candidate tables."
        ),
    )
    def engineering_db_lookup_tool(
        query: str,
        candidate_tables: list[str] | None = None,
        max_tables: int = 5,
        max_rows_per_table: int = 5,
    ) -> dict:
        return engineering_db_lookup(
            query=query,
            candidate_tables=candidate_tables,
            max_tables=max_tables,
            max_rows_per_table=max_rows_per_table,
        ).to_dict()
