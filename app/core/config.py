import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


class Settings:
    def __init__(self) -> None:
        self.db_name = os.getenv("DB_NAME")
        self.db_user = os.getenv("DB_USER")
        self.db_password = os.getenv("DB_PASSWORD")
        self.db_host = os.getenv("DB_HOST")
        self.db_port = os.getenv("DB_PORT")
        self.db_schema = os.getenv("DB_SCHEMA", "public")
        vault_root = os.getenv("JARVIS_VAULT_ROOT") or os.getenv("PROJECT_PATH", "")
        self.vault_root = Path(vault_root).expanduser() if vault_root else None
        self.mcp_transport = os.getenv("MCP_TRANSPORT", "streamable-http")
        self.mcp_host = os.getenv("MCP_HOST", "0.0.0.0")
        self.mcp_port = int(os.getenv("MCP_PORT", "8000"))
        self.mcp_mount_path = os.getenv("MCP_MOUNT_PATH", "/")
        self.mcp_streamable_http_path = os.getenv("MCP_STREAMABLE_HTTP_PATH", "/mcp")
        self.mcp_name = os.getenv("MCP_SERVER_NAME", "jarvis")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
