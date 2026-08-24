from __future__ import annotations

from pathlib import Path

from app.services.second_brain import read_manifest, write_manifest


def test_manifest_is_created_atomically(tmp_path: Path) -> None:
    path = tmp_path / "state" / "manifest.json"
    empty = read_manifest(path)
    assert empty["last_processed_commit"] is None
    empty["last_processed_commit"] = "abc123"
    write_manifest(path, empty)
    assert read_manifest(path)["last_processed_commit"] == "abc123"
