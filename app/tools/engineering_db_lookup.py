from mcp.server.fastmcp import FastMCP

from app.services.engineering_db import engineering_db_lookup


def register(server: FastMCP) -> None:
    @server.tool(
        name="engineering-db-lookup",
        description=(
            "Query the engineering DB for structured results. "
            "Use search_term for only the core identifier, model, part number, label, wire ID, or short lookup value. "
            "Do not place instructions, output formatting, or field requests inside search_term. "
            "Use candidate_tables to narrow scope, requested_fields to indicate which fields matter, "
            "entity_hint to suggest record type, and follow_relationships when related records may matter."
        ),
    )
    def engineering_db_lookup_tool(
        search_term: str,
        candidate_tables: list[str] | None = None,
        requested_fields: list[str] | None = None,
        entity_hint: str | None = None,
        follow_relationships: bool = False,
        max_tables: int = 5,
        max_rows_per_table: int = 5,
    ) -> dict:
        """Look up engineering DB records using a short search term.

        Args:
            search_term: Only the core value to search for, for example "RPI4B", "XT60", or "W001".
            candidate_tables: Optional table allowlist such as ["components", "interfaces"].
            requested_fields: Optional output fields the caller cares about, such as ["component_id", "name", "notes_path"].
            entity_hint: Optional hint like "component", "interface", "wire", or "cable".
            follow_relationships: Whether relationship context should be emphasized in the returned summaries.
            max_tables: Maximum number of tables to search.
            max_rows_per_table: Maximum rows to return per searched table.
        """
        return engineering_db_lookup(
            search_term=search_term,
            candidate_tables=candidate_tables,
            requested_fields=requested_fields,
            entity_hint=entity_hint,
            follow_relationships=follow_relationships,
            max_tables=max_tables,
            max_rows_per_table=max_rows_per_table,
        ).to_dict()
