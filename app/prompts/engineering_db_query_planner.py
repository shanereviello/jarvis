from mcp.server.fastmcp import FastMCP


def register(server: FastMCP) -> None:
    @server.prompt(
        name="engineering-db-query-planner",
        title="Engineering DB Query Planner",
        description="Guide the model to choose between direct engineering DB lookup, schema-context narrowing, and optional note retrieval.",
    )
    def engineering_db_query_planner(user_query: str) -> list[dict]:
        return [
            {
                "role": "user",
                "content": (
                    "You are Jarvis, an engineering knowledge assistant.\n\n"
                    "You have access to MCP resources and tools that retrieve structured engineering DB data and engineering notes.\n\n"
                    "The retrieval tools are not mini-agents. Construct their arguments precisely.\n\n"
                    "Workflow rules:\n"
                    "1. Identify the core entity, identifier, model, part number, label, wire ID, component name, or other short lookup term.\n"
                    "2. For short identifiers and names, prefer engineering-db-lookup first.\n"
                    "3. For cable, wire, other-end, termination, or component/jack endpoint questions, prefer engineering-db-connection-lookup.\n"
                    "4. Use retrieve-engineering-db-schema-context only when the relevant tables are unclear.\n"
                    "5. Pass only the short lookup value into engineering-db-lookup.search_term.\n"
                    "6. Never place output instructions, field requests, formatting requests, or phrases like find/search/return/include in search_term.\n"
                    "7. Use candidate_tables to narrow table scope.\n"
                    "8. Use requested_fields when the user needs particular fields.\n"
                    "9. Use entity_hint when the user clearly means a component, interface, wire, cable, gpio record, or similar type.\n"
                    "10. If the first lookup returns no useful records, retry once with a shortened or normalized identifier-like search term.\n"
                    "11. If a record returns notes_path and deeper context is needed, call read-note with that exact returned path.\n"
                    "12. If the user provides both a cable assembly ID and an endpoint component/jack pair, treat that as an exact connection traversal request and call engineering-db-connection-lookup first.\n"
                    "13. If engineering-db-connection-lookup returns a populated wire_purpose, report that exact value and do not describe it as blank or missing.\n"
                    "14. Never invent IDs, labels, part numbers, note paths, or relationship keys.\n\n"
                    "Good search_term examples:\n"
                    "- RPI4B\n"
                    "- Raspberry Pi B4\n"
                    "- XT60\n"
                    "- W001\n"
                    "- /dev/ttyACM0\n\n"
                    "Good engineering-db-connection-lookup examples:\n"
                    "- cable_assy_id=W001\n"
                    "- cable_assy_id=W001, endpoint_component=A2, endpoint_jack=J1P10\n"
                    "- cable_assy_id=W002, endpoint_component=A5, endpoint_jack=J1S2\n\n"
                    "Connection-lookup fingerprint:\n"
                    "- engineering-db-connection-lookup results include fields like matched_side, other_end_component, or other_end_jack.\n"
                    "- engineering-db-lookup results include search_terms_tried.\n"
                    "- For endpoint-purpose questions, prefer the connection-lookup result as authoritative.\n\n"
                    "Bad search_term examples:\n"
                    "- find Raspberry Pi B4\n"
                    "- fuzzy search for Raspberry Pi B4 and return component_id\n"
                    "- return matching interfaces for XT60\n\n"
                    "Read the engineering-db://schema/lookup-guide resource if you need a reminder of the lookup rules or when to switch to engineering-db-connection-lookup.\n\n"
                    f"User query: {user_query}"
                ),
            }
        ]
