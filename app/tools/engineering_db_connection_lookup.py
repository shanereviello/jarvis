from mcp.server.fastmcp import FastMCP

from app.services.engineering_db import engineering_db_connection_lookup


def register(server: FastMCP) -> None:
    @server.tool(
        name="engineering-db-connection-lookup",
        description=(
            "Perform deterministic cable and wire endpoint lookup against wire_list. "
            "Use this when the user asks where a cable goes, what the other end is, "
            "what connects to a component/jack pair, or what purpose a specific wire row has. "
            "Pass cable_assy_id like W001, and optionally endpoint_component and endpoint_jack for exact endpoint matching."
        ),
    )
    def engineering_db_connection_lookup_tool(
        cable_assy_id: str,
        endpoint_component: str | None = None,
        endpoint_jack: str | None = None,
        requested_fields: list[str] | None = None,
        max_rows: int = 50,
    ) -> dict:
        """Trace exact wire_list rows for cable and endpoint questions.

        Args:
            cable_assy_id: Cable assembly ID, for example "W001".
            endpoint_component: Optional endpoint component label, for example "A2".
            endpoint_jack: Optional endpoint jack label, for example "J1P10".
            requested_fields: Optional list of fields the caller cares about.
            max_rows: Maximum number of matching wire_list rows to return.
        """
        return engineering_db_connection_lookup(
            cable_assy_id=cable_assy_id,
            endpoint_component=endpoint_component,
            endpoint_jack=endpoint_jack,
            requested_fields=requested_fields,
            max_rows=max_rows,
        ).to_dict()
