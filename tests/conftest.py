from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from app.core.config import get_settings


def _git(*args: str, cwd: Path) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)
    return result.stdout.strip()


@pytest.fixture()
def notes_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    source = tmp_path / "source"
    source.mkdir()
    _git("init", "-b", "main", cwd=source)
    _git("config", "user.email", "tests@example.invalid", cwd=source)
    _git("config", "user.name", "Jarvis Tests", cwd=source)
    (source / "Engineering").mkdir()
    (source / "Engineering" / "IMU.md").write_text(
        "---\ntitle: IMU\nproject: robot\n---\n\n# Purpose\n\nCanonical sensor note.\n\n## Interface\n\nSee [[Engineering/Localization]].\n",
        encoding="utf-8",
    )
    (source / "Engineering" / "Localization.md").write_text(
        "# Localization\n\nUses [[IMU]].\n",
        encoding="utf-8",
    )
    _git("add", ".", cwd=source)
    _git("commit", "-m", "baseline notes", cwd=source)

    bare = tmp_path / "repo.git"
    _git("clone", "--bare", str(source), str(bare), cwd=tmp_path)
    baseline = tmp_path / "baseline"
    review = tmp_path / "review"
    _git("--git-dir", str(bare), "worktree", "add", "--detach", str(baseline), "main", cwd=tmp_path)
    _git("--git-dir", str(bare), "worktree", "add", "-b", "jarvis/review", str(review), "main", cwd=tmp_path)
    (review / "Jarvis Drafts").mkdir()
    (review / "Jarvis Second Brain").mkdir()

    audit = tmp_path / "audit" / "note-actions.jsonl"
    monkeypatch.setenv("JARVIS_NOTES_REPOSITORY", str(bare))
    monkeypatch.setenv("JARVIS_NOTES_BASELINE", str(baseline))
    monkeypatch.setenv("JARVIS_NOTES_REVIEW", str(review))
    monkeypatch.setenv("JARVIS_DRAFT_ROOT", "Jarvis Drafts")
    monkeypatch.setenv("JARVIS_SECOND_BRAIN_ROOT", "Jarvis Second Brain")
    monkeypatch.setenv("JARVIS_AUDIT_PATH", str(audit))
    monkeypatch.setenv("JARVIS_NOTES_MAX_RESULTS", "100")
    monkeypatch.setenv("JARVIS_NOTES_MAX_CONTENT_BYTES", "100000")
    get_settings.cache_clear()
    yield {"source": source, "bare": bare, "baseline": baseline, "review": review, "audit": audit}
    get_settings.cache_clear()
