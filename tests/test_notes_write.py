from __future__ import annotations

import json
import subprocess
from pathlib import Path

import yaml

from app.services.notes_repository import calculate_sha256, parse_frontmatter
from app.services.notes_writer import notes_write


def test_create_attributes_draft_without_committing(notes_environment: dict[str, Path]) -> None:
    result = notes_write(
        "create",
        path="Jarvis Drafts/Calibration.md",
        title="Calibration",
        content="# Procedure\n\nRun the calibration.",
        sources=["Engineering/IMU.md"],
    )
    assert result.status == "success"
    target = notes_environment["review"] / "Jarvis Drafts" / "Calibration.md"
    metadata, body = parse_frontmatter(target.read_text(encoding="utf-8"))
    assert metadata["created_by"] == "jarvis"
    assert metadata["review_status"] == "pending"
    assert metadata["source_revision"]
    assert "Jarvis-written draft" in body
    status = subprocess.run(
        ["git", "status", "--short", "--", "Jarvis Drafts/Calibration.md"],
        cwd=notes_environment["review"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert status.startswith("??")


def test_create_refuses_existing_file(notes_environment: dict[str, Path]) -> None:
    first = notes_write("create", path="Jarvis Drafts/Test.md", title="Test", content="First")
    second = notes_write("create", path="Jarvis Drafts/Test.md", title="Test", content="Second")
    assert first.status == "success"
    assert second.status == "conflict"


def test_hash_conflict_preserves_human_edit(notes_environment: dict[str, Path]) -> None:
    notes_write("create", path="Jarvis Drafts/Test.md", title="Test", content="Initial")
    target = notes_environment["review"] / "Jarvis Drafts" / "Test.md"
    stale_hash = calculate_sha256(target)
    target.write_text(target.read_text(encoding="utf-8") + "Human edit\n", encoding="utf-8")
    result = notes_write("replace_draft", path="Jarvis Drafts/Test.md", content="Replacement", expected_hash=stale_hash)
    assert result.status == "conflict"
    assert "Human edit" in target.read_text(encoding="utf-8")


def test_update_section_preserves_unrelated_content(notes_environment: dict[str, Path]) -> None:
    notes_write(
        "create",
        path="Jarvis Second Brain/System.md",
        title="System",
        content="# Purpose\n\nOld.\n\n# Interfaces\n\nPreserve this.",
    )
    target = notes_environment["review"] / "Jarvis Second Brain" / "System.md"
    current_hash = calculate_sha256(target)
    result = notes_write(
        "update_section",
        path="Jarvis Second Brain/System.md",
        heading="Purpose",
        content="New.",
        expected_hash=current_hash,
    )
    assert result.status == "success"
    body = parse_frontmatter(target.read_text(encoding="utf-8"))[1]
    assert "New." in body
    assert "Preserve this." in body


def test_refuses_modifying_human_authored_file(notes_environment: dict[str, Path]) -> None:
    target = notes_environment["review"] / "Jarvis Drafts" / "Human.md"
    target.write_text("---\ncreated_by: shane\n---\n\nHuman content.\n", encoding="utf-8")
    result = notes_write("append", path="Jarvis Drafts/Human.md", content="Jarvis text")
    assert result.status == "refused"
    assert "Jarvis text" not in target.read_text(encoding="utf-8")


def test_audits_write_actions_without_note_content(notes_environment: dict[str, Path]) -> None:
    notes_write("create", path="Jarvis Drafts/Audit.md", title="Audit", content="SENSITIVE_NOTE_BODY")
    records = [json.loads(line) for line in notes_environment["audit"].read_text(encoding="utf-8").splitlines()]
    assert records[-1]["path"] == "Jarvis Drafts/Audit.md"
    assert "SENSITIVE_NOTE_BODY" not in notes_environment["audit"].read_text(encoding="utf-8")
