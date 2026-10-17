import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("package_release", ROOT / "deploy/package_release.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def command(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args]).decode().strip()


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    command(root, "init", "-q")
    command(root, "config", "user.email", "fixture@example.invalid")
    command(root, "config", "user.name", "Fixture")
    (root / "app").mkdir()
    (root / "app/main.py").write_text("original\n")
    (root / "requirements.txt").write_text("fixture==1\n")
    command(root, "add", ".")
    command(root, "commit", "-qm", "fixture")
    return root


def test_export_uses_commit_not_dirty_or_private_worktree(repo, tmp_path):
    commit = command(repo, "rev-parse", "HEAD")
    (repo / "app/main.py").write_text("dirty\n")
    (repo / ".env").write_text("private fixture\n")
    output = tmp_path / "release"
    digest = module.package(repo, commit, "mcp", output)
    assert (output / "app/main.py").read_text() == "original\n"
    assert not (output / ".env").exists()
    manifest = json.loads((output / "release-manifest.json").read_text())
    assert manifest["source_commit"] == commit
    assert manifest["activation"] is False
    assert len(digest) == 64
    with pytest.raises(FileExistsError):
        module.package(repo, commit, "mcp", output)


def test_export_refuses_selected_symlink_before_allocating(repo, tmp_path):
    (repo / "app/link").symlink_to("/etc/passwd")
    command(repo, "add", ".")
    command(repo, "commit", "-qm", "symlink")
    output = tmp_path / "release"
    with pytest.raises(ValueError, match="nonregular"):
        module.package(repo, "HEAD", "mcp", output)
    assert not output.exists()


def test_export_refuses_tracked_private_config(repo, tmp_path):
    (repo / "app/.env").write_text("private fixture")
    command(repo, "add", ".")
    command(repo, "commit", "-qm", "private fixture")
    with pytest.raises(ValueError, match="private configuration"):
        module.package(repo, "HEAD", "mcp", tmp_path / "release")


def test_clean_source_docker_copy_inputs_exist():
    # Every local COPY input must survive a fresh tracked-source checkout.
    for line in (ROOT / "Dockerfile").read_text().splitlines():
        if line.startswith("COPY "):
            source = line.split()[1]
            assert (ROOT / source).exists(), source
