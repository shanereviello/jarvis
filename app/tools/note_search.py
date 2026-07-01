from pathlib import Path

from app.config import PROJECT_PATH


def read_note_content(notes_path: str) -> dict:
    path = Path(PROJECT_PATH) / notes_path

    if not path.exists():
        return {
            "ok": False,
            "notes_path": notes_path,
            "error": "Note file not found.",
        }

    content = path.read_text(errors="ignore")[:8000]
    return {
        "ok": True,
        "notes_path": notes_path,
        "content": content,
    }
