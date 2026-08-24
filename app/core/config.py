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
        legacy_vault_root = os.getenv("JARVIS_VAULT_ROOT") or os.getenv("PROJECT_PATH", "")
        baseline_root = os.getenv("JARVIS_NOTES_BASELINE") or legacy_vault_root
        review_root = os.getenv("JARVIS_NOTES_REVIEW", "")
        repository_root = os.getenv("JARVIS_NOTES_REPOSITORY", "")
        self.vault_root = Path(baseline_root).expanduser() if baseline_root else None
        self.notes_baseline_root = self.vault_root
        self.notes_review_root = Path(review_root).expanduser() if review_root else None
        self.notes_repository_root = Path(repository_root).expanduser() if repository_root else None
        self.notes_baseline_ref = os.getenv("JARVIS_NOTES_BASELINE_REF", "main")
        self.notes_draft_root = os.getenv("JARVIS_DRAFT_ROOT", "Jarvis Drafts")
        self.notes_second_brain_root = os.getenv("JARVIS_SECOND_BRAIN_ROOT", "Jarvis Second Brain")
        self.notes_max_results = int(os.getenv("JARVIS_NOTES_MAX_RESULTS", "100"))
        self.notes_max_content_bytes = int(os.getenv("JARVIS_NOTES_MAX_CONTENT_BYTES", "100000"))
        audit_path = os.getenv("JARVIS_AUDIT_PATH", "")
        self.audit_path = Path(audit_path).expanduser() if audit_path else None
        self.mcp_transport = os.getenv("MCP_TRANSPORT", "streamable-http")
        self.mcp_host = os.getenv("MCP_HOST", "0.0.0.0")
        self.mcp_port = int(os.getenv("MCP_PORT", "8000"))
        self.mcp_mount_path = os.getenv("MCP_MOUNT_PATH", "/")
        self.mcp_streamable_http_path = os.getenv("MCP_STREAMABLE_HTTP_PATH", "/mcp")
        self.mcp_name = os.getenv("MCP_SERVER_NAME", "jarvis")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
