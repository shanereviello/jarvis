from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from app.services.engineering_db import (
    get_engineering_db_schema_catalog,
    get_engineering_db_table_schema,
)


def register(server: FastMCP) -> None:
    @server.resource(
        "engineering-db://schema/catalog",
        name="engineering-db-schema-catalog",
        description="Catalog of engineering DB tables, columns, searchable fields, and note-related fields.",
        mime_type="application/json",
    )
    def engineering_db_schema_catalog() -> str:
        return json.dumps(get_engineering_db_schema_catalog().to_dict(), indent=2)

    @server.resource(
        "engineering-db://schema/relationships",
        name="engineering-db-schema-relationships",
        description="Foreign-key style relationships between engineering DB tables.",
        mime_type="application/json",
    )
    def engineering_db_schema_relationships() -> str:
        catalog = get_engineering_db_schema_catalog()
        payload = {
            "ok": catalog.ok,
            "schema_name": catalog.schema_name,
            "relationships": [relationship.to_dict() for relationship in catalog.relationships],
            "error": catalog.error,
        }
        return json.dumps(payload, indent=2)

    @server.resource(
        "engineering-db://schema/table/{table_name}",
        name="engineering-db-table-schema",
        description="Schema details for one engineering DB table.",
        mime_type="application/json",
    )
    def engineering_db_table_schema(table_name: str) -> str:
        table = get_engineering_db_table_schema(table_name)
        payload = {
            "ok": table is not None,
            "table": table.to_dict() if table is not None else None,
            "error": None if table is not None else f"Table '{table_name}' was not found in the configured DB schema.",
        }
        return json.dumps(payload, indent=2)
