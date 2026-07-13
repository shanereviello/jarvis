from mcp.server.fastmcp import FastMCP

from app.core.config import get_settings
from app.servers.mcp.registry import register_tools


def create_server() -> FastMCP:
    settings = get_settings()
    server = FastMCP(
        name=settings.mcp_name,
        instructions=(
            "Jarvis MCP server for engineering DB exploration and vault note retrieval. "
            "Start by reading engineering DB schema resources or calling retrieve-engineering-db-schema-context. "
            "Then use engineering-db-lookup with narrowed tables. Only use read-note when the DB result is not sufficient."
        ),
        host=settings.mcp_host,
        port=settings.mcp_port,
        mount_path=settings.mcp_mount_path,
        streamable_http_path=settings.mcp_streamable_http_path,
    )
    register_tools(server)
    return server


def main() -> None:
    settings = get_settings()
    server = create_server()
    server.run(settings.mcp_transport, mount_path=settings.mcp_mount_path)


if __name__ == "__main__":
    main()
