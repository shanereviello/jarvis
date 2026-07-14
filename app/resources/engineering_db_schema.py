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
        description="Catalog of engineering DB tables, columns, searchable fields, note-related fields, and lookup hints.",
        mime_type="application/json",
    )
    def engineering_db_schema_catalog() -> str:
        return json.dumps(get_engineering_db_schema_catalog().to_dict(), indent=2)

    @server.resource(
        "engineering-db://schema/lookup-guide",
        name="engineering-db-lookup-guide",
        description="Guidance for when to use schema context, how to choose search terms, and how to shape engineering DB lookups.",
        mime_type="application/json",
    )
    def engineering_db_lookup_guide() -> str:
        payload = {
            "search_term_rules": [
                "Pass only the core identifier, model, part number, label, wire ID, connector name, or short entity name.",
                "Do not include instructions like find, search, return, include, show, or fuzzy search.",
                "Do not include requested fields or output formatting in search_term.",
            ],
            "when_to_use_schema_context": [
                "Use retrieve-engineering-db-schema-context for broad natural-language questions when the tables are unclear.",
                "Skip schema context for short identifiers like RPI4B, XT60, W001, GPIO14, or /dev/ttyACM0.",
            ],
            "lookup_argument_guide": {
                "search_term": "Only the short value to search for.",
                "candidate_tables": "Optional table allowlist when you know the likely tables.",
                "requested_fields": "Optional list of fields the caller wants to extract after retrieval.",
                "entity_hint": "Optional type hint like component, interface, wire, cable, or gpio.",
                "follow_relationships": "Set true when related records matter for the answer.",
            },
            "connection_lookup_argument_guide": {
                "cable_assy_id": "Required cable assembly ID such as W001 or W002.",
                "endpoint_component": "Optional exact endpoint component label such as A2.",
                "endpoint_jack": "Optional exact endpoint jack such as J1P10.",
                "requested_fields": "Optional list of fields to emphasize in the returned connection rows.",
                "max_rows": "Maximum number of exact wire_list rows to return.",
            },
            "when_to_use_connection_lookup": [
                "Use engineering-db-connection-lookup when the question is about where a cable goes.",
                "Use it when the user asks what the other end is for a component/jack endpoint.",
                "Use it when you need exact wire_list fields like component_a, jack_a, component_b, jack_b, or wire_purpose.",
            ],
            "schema_metadata_guide": {
                "entity_type": "The inferred kind of record a table represents. Customize this if your table naming differs.",
                "best_lookup_columns": "Columns the retrieval layer currently treats as the strongest entry points.",
                "common_question_types": "Examples of the kinds of user questions this table is meant to answer.",
                "related_tables": "Tables linked through foreign-key style relationships.",
                "recommended_followup_tables": "Tables the agent should consider after a first successful match.",
            },
            "customization_notes": [
                "Tune the DB knowledge map heuristics in app/services/engineering_db.py.",
                "Look for helper functions like _infer_entity_type, _infer_best_lookup_columns, and _infer_common_question_types.",
            ],
        }
        return json.dumps(payload, indent=2)

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
        description="Schema details and lookup hints for one engineering DB table.",
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
