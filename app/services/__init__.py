from __future__ import annotations

import importlib
from typing import Any

__all__ = [
    "engineering_db_lookup",
    "get_engineering_db_schema_catalog",
    "read_note",
    "retrieve_engineering_db_schema_context",
]


def __getattr__(name: str) -> Any:
    """Preserve package exports without importing optional drivers eagerly."""
    if name == "read_note":
        from app.services.notes import read_note

        return read_note
    if name in {
        "engineering_db_lookup",
        "get_engineering_db_schema_catalog",
        "retrieve_engineering_db_schema_context",
    }:
        engineering_db = importlib.import_module("app.services.engineering_db")
        return getattr(engineering_db, name)
    raise AttributeError(name)
