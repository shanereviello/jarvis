import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("stage_release", ROOT / "deploy/mcp/stage_release.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixture_candidate(tmp_path):
    root = tmp_path / "candidate"
    root.mkdir()
    files = {}
    for name in ["Dockerfile", "deploy/mcp/compose.release.yml", "deploy/mcp/requirements.lock"]:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fixture\n")
        files[name] = {"mode": "100644", "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    manifest = {"schema_version": 1, "service": "mcp", "activation": False,
                "source_commit": "a" * 40, "files": files}
    raw = json.dumps(manifest).encode()
    (root / "release-manifest.json").write_bytes(raw)
    return root, hashlib.sha256(raw).hexdigest()


def test_stage_preflight_detects_content_change_before_privileged_writes(tmp_path):
    root, expected = fixture_candidate(tmp_path)
    assert module.payload(root, expected)[0] == "a" * 40
    (root / "Dockerfile").write_text("changed")
    with pytest.raises(ValueError, match="member changed"):
        module.payload(root, expected)


def test_stage_preflight_refuses_symlink(tmp_path):
    root, expected = fixture_candidate(tmp_path)
    path = root / "Dockerfile"
    path.unlink()
    path.symlink_to(root / "deploy/mcp/requirements.lock")
    with pytest.raises(OSError):
        module.payload(root, expected)


def test_stage_preflight_refuses_changed_manifest(tmp_path):
    root, expected = fixture_candidate(tmp_path)
    (root / "release-manifest.json").write_text("{}")
    with pytest.raises(ValueError, match="manifest changed"):
        module.payload(root, expected)


def test_stage_requires_root_before_reading_candidate(monkeypatch):
    monkeypatch.setattr(module.os, "geteuid", lambda: 1000)
    with pytest.raises(ValueError, match="administrator"):
        module.stage(Path("/absent"), "0" * 64)
