from pathlib import Path

from agents import function_tool

from app.config import PROJECT_PATH


@function_tool
def read_note(notes_path: str) -> str:
    """
    Read an engineering note from the local NAS/Obsidian vault.
    Use this after finding a component with a notes_path.
    """

    path = Path(PROJECT_PATH) / notes_path

    if not path.exists():
        return f"Note file not found: {notes_path}"

    return path.read_text(errors="ignore")[:8000]

