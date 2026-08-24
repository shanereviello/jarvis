from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from typing import Any

from app.core.config import get_settings


_AUDIT_LOCK = threading.Lock()


def record_note_action(event: dict[str, Any]) -> None:
    path = get_settings().audit_path
    if path is None:
        return
    payload = {"timestamp": datetime.now(timezone.utc).isoformat(), "actor": "jarvis", **event}
    path.parent.mkdir(parents=True, exist_ok=True)
    with _AUDIT_LOCK, path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, sort_keys=True, default=str) + "\n")
