from __future__ import annotations

from pathlib import Path

import pytest

from app.services.notes_repository import NotesRepositoryError, resolve_baseline_path, resolve_review_path


def test_rejects_traversal_and_non_markdown(notes_environment: dict[str, Path]) -> None:
    with pytest.raises(NotesRepositoryError):
        resolve_baseline_path("../secret.md")
    with pytest.raises(NotesRepositoryError):
        resolve_baseline_path("Engineering/data.csv")


def test_rejects_protected_paths(notes_environment: dict[str, Path]) -> None:
    with pytest.raises(NotesRepositoryError) as error:
        resolve_baseline_path(".obsidian/workspace.md")
    assert error.value.error_code == "PROTECTED_PATH"


def test_rejects_symlink_escape(notes_environment: dict[str, Path], tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (notes_environment["baseline"] / "escape").symlink_to(outside, target_is_directory=True)
    with pytest.raises(NotesRepositoryError) as error:
        resolve_baseline_path("escape/secret.md")
    assert error.value.error_code == "OUTSIDE_ALLOWED_ROOT"


def test_writes_are_limited_to_jarvis_roots(notes_environment: dict[str, Path]) -> None:
    assert resolve_review_path("Jarvis Drafts/Test.md").name == "Test.md"
    with pytest.raises(NotesRepositoryError) as error:
        resolve_review_path("Engineering/Test.md")
    assert error.value.error_code == "OUTSIDE_ALLOWED_ROOT"
