from __future__ import annotations

import subprocess
from pathlib import Path

from app.services.notes_reader import notes_read


def test_reads_only_materialized_baseline(notes_environment: dict[str, Path]) -> None:
    (notes_environment["review"] / "Jarvis Drafts" / "Pending.md").write_text("Pending secret", encoding="utf-8")
    result = notes_read("list", limit=100)
    paths = {item["path"] for item in result.data["notes"]}
    assert "Engineering/IMU.md" in paths
    assert "Jarvis Drafts/Pending.md" not in paths


def test_read_returns_commit_hash_metadata_and_headings(notes_environment: dict[str, Path]) -> None:
    result = notes_read("read", path="Engineering/IMU.md")
    assert result.status == "success"
    assert result.baseline_commit
    assert result.data["frontmatter"]["title"] == "IMU"
    assert result.data["content_hash"].startswith("sha256:")
    assert result.data["headings"][0]["heading"] == "Purpose"


def test_search_links_backlinks_and_resolution(notes_environment: dict[str, Path]) -> None:
    search = notes_read("search", query="Canonical sensor")
    assert search.data["notes"][0]["path"] == "Engineering/IMU.md"
    assert search.data["returned_note_count"] == 1
    assert search.data["total_match_count"] == 1

    links = notes_read("outgoing_links", path="Engineering/IMU.md")
    assert "Engineering/Localization" in links.data["links"]

    backlinks = notes_read("backlinks", path="Engineering/IMU.md")
    assert {item["path"] for item in backlinks.data["backlinks"]} == {"Engineering/Localization.md"}

    resolved = notes_read("resolve_link", query="IMU")
    assert resolved.data["candidates"] == ["Engineering/IMU.md"]


def test_read_rejects_uncommitted_human_path(notes_environment: dict[str, Path]) -> None:
    (notes_environment["source"] / "Private.md").write_text("Not committed", encoding="utf-8")
    result = notes_read("read", path="Private.md")
    assert result.status == "not_found"


def test_browse_discovers_directories_and_immediate_notes(notes_environment: dict[str, Path]) -> None:
    root = notes_read("browse")
    assert root.data["directories"] == ["Engineering"]
    assert root.data["directory_count"] == 1
    assert root.data["complete"] is True

    engineering = notes_read("browse", directory="Engineering")
    assert engineering.data["note_count"] == 2
    assert {note["path"] for note in engineering.data["notes"]} == {
        "Engineering/IMU.md",
        "Engineering/Localization.md",
    }


def test_recursive_and_non_recursive_lists_are_explicit(notes_environment: dict[str, Path]) -> None:
    nested = notes_environment["baseline"] / "Engineering" / "Nested"
    nested.mkdir()
    (nested / "Deep.md").write_text("# Deep\n", encoding="utf-8")

    shallow = notes_read("list", directory="Engineering", recursive=False, limit=100)
    recursive = notes_read("list", directory="Engineering", recursive=True, limit=100)
    assert shallow.data["total_count"] == 2
    assert recursive.data["total_count"] == 3
    assert shallow.data["recursive"] is False
    assert recursive.data["recursive"] is True


def test_list_pagination_returns_every_note_once(notes_environment: dict[str, Path]) -> None:
    generated = notes_environment["baseline"] / "Generated"
    generated.mkdir()
    for index in range(105):
        (generated / f"Note-{index}.md").write_text(f"# Note {index}\n", encoding="utf-8")

    cursor = None
    paths: list[str] = []
    pages = 0
    while True:
        result = notes_read("list", directory="Generated", limit=100, cursor=cursor)
        paths.extend(note["path"] for note in result.data["notes"])
        pages += 1
        if not result.data["has_more"]:
            assert result.data["complete"] is True
            assert result.data["next_cursor"] is None
            break
        assert result.data["complete"] is False
        cursor = result.data["next_cursor"]

    assert pages == 2
    assert len(paths) == len(set(paths)) == 105


def test_baseline_change_invalidates_list_cursor(notes_environment: dict[str, Path]) -> None:
    first = notes_read("list", limit=1)
    cursor = first.data["next_cursor"]
    assert cursor

    baseline = notes_environment["baseline"]
    subprocess.run(["git", "config", "user.email", "tests@example.invalid"], cwd=baseline, check=True)
    subprocess.run(["git", "config", "user.name", "Jarvis Tests"], cwd=baseline, check=True)
    (baseline / "Changed.md").write_text("# Changed\n", encoding="utf-8")
    subprocess.run(["git", "add", "Changed.md"], cwd=baseline, check=True)
    subprocess.run(["git", "commit", "-m", "advance baseline"], cwd=baseline, check=True, capture_output=True)

    result = notes_read("list", limit=1, cursor=cursor)
    assert result.status == "conflict"
    assert result.error_code == "BASELINE_CHANGED"


def test_search_rejects_wildcard_discovery(notes_environment: dict[str, Path]) -> None:
    result = notes_read("search", query="*")
    assert result.status == "refused"
    assert result.error_code == "WILDCARD_NOT_SUPPORTED"
    assert "browse or list" in result.message


def test_search_groups_matches_by_note_and_limits_excerpts(notes_environment: dict[str, Path]) -> None:
    result = notes_read("search", query="IMU", max_matches_per_note=1)
    assert result.status == "success"
    assert result.data["total_note_count"] == 2
    assert result.data["total_match_count"] == 2
    assert all(len(note["matches"]) <= 1 for note in result.data["notes"])
    assert result.data["complete"] is True


def test_search_paginates_by_note_and_cursor_is_request_bound(notes_environment: dict[str, Path]) -> None:
    generated = notes_environment["baseline"] / "Searchable"
    generated.mkdir()
    for index in range(3):
        (generated / f"Match-{index}.md").write_text("needle\nneedle\n", encoding="utf-8")

    first = notes_read("search", directory="Searchable", query="needle", limit=2)
    assert first.data["returned_note_count"] == 2
    assert first.data["total_note_count"] == 3
    assert first.data["total_match_count"] == 6
    assert first.data["has_more"] is True
    assert first.data["complete"] is False

    second = notes_read(
        "search",
        directory="Searchable",
        query="needle",
        limit=2,
        cursor=first.data["next_cursor"],
    )
    assert second.data["returned_note_count"] == 1
    assert second.data["has_more"] is False
    assert second.data["complete"] is True

    mismatched = notes_read(
        "search",
        directory="Searchable",
        query="different",
        limit=2,
        cursor=first.data["next_cursor"],
    )
    assert mismatched.status == "refused"
    assert mismatched.error_code == "CURSOR_REQUEST_MISMATCH"


def test_inventory_totals_match_complete_list(notes_environment: dict[str, Path]) -> None:
    inventory = notes_read("inventory")
    listed = notes_read("list", limit=100)
    assert inventory.data["total_notes"] == listed.data["total_count"] == 2
    assert inventory.data["tree"] == [
        {"path": "Engineering", "type": "directory", "note_count_recursive": 2}
    ]
    assert inventory.data["complete"] is True


def test_operation_specific_arguments_are_rejected(notes_environment: dict[str, Path]) -> None:
    result = notes_read("list", query="not valid")
    assert result.status == "refused"
    assert result.error_code == "INVALID_INPUT"
