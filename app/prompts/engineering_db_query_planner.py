from mcp.server.fastmcp import FastMCP


def register(server: FastMCP) -> None:
    @server.prompt(
        name="engineering-db-query-planner",
        title="Engineering DB Query Planner",
        description="Guide the model to inspect engineering DB schema context before querying the database.",
    )
    def engineering_db_query_planner(user_query: str) -> list[dict]:
        return [
            {
                "role": "user",
                "content": (
                    "You are planning an engineering DB lookup. "
                    "For the query below, first inspect the available engineering DB schema resources or call "
                    "retrieve-engineering-db-schema-context. Use the suggested tables to scope engineering-db-lookup. "
                    "Only call read-note if the database result is insufficient or a notes path clearly adds value.\n\n"
                    f"User query: {user_query}"
                ),
            }
        ]
