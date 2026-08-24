from __future__ import annotations

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
    assert search.data["matches"][0]["path"] == "Engineering/IMU.md"

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
