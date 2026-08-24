from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def read_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"last_processed_commit": None, "last_successful_run": None, "generated_notes": {}}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Second-brain manifest must contain a JSON object.")
    payload.setdefault("generated_notes", {})
    return payload


def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(manifest, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
