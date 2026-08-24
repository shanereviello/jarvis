from mcp.server.fastmcp import FastMCP

from app.core.config import get_settings
from app.servers.mcp.registry import register_tools


def create_server() -> FastMCP:
    settings = get_settings()
    server = FastMCP(
        name=settings.mcp_name,
        instructions=(
            "Jarvis MCP server for engineering DB exploration and approved-baseline note access. "
            "Start by reading engineering DB schema resources or calling retrieve-engineering-db-schema-context. "
            "Then use engineering-db-lookup with narrowed tables. Use notes-read for the approved Git baseline. "
            "For notes, use browse to discover directories, inventory for a structural summary, list to enumerate files, "
            "and search only for literal text; search does not support wildcards, glob patterns, or regular expressions. "
            "Follow pagination cursors until has_more is false before claiming a list or search is complete. "
            "Use notes-write only for reviewable Jarvis drafts; its output is not authoritative until a human approves "
            "and commits it. Never treat review-worktree drafts as verified source material."
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
