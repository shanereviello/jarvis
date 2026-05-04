# memory.py
import datetime
import json
import os
import re

MEMORY_ROOT = "memory"
RAW_DIR = os.path.join(MEMORY_ROOT, "raw")
EPISODIC_DIR = os.path.join(MEMORY_ROOT, "episodic")
SEMANTIC_DIR = os.path.join(MEMORY_ROOT, "semantic")
EMBEDDINGS_DIR = os.path.join(MEMORY_ROOT, "embeddings")
INDEXES_DIR = os.path.join(MEMORY_ROOT, "indexes")
SUMMARIES_DIR = os.path.join(MEMORY_ROOT, "summaries")

RAW_CATEGORIES = ["conversations", "calendar", "system", "notes"]
SEMANTIC_CATEGORIES = ["preferences", "projects", "people", "tasks"]

MIGRATION_MARKER = os.path.join(MEMORY_ROOT, ".memory_migration_complete")


def _now_iso():
    return datetime.datetime.now().replace(microsecond=0).isoformat()


def _safe_filename(value):
    value = str(value)
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value)
    return value.strip("-._ ")[:180] or "memory"


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _read_json_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _load_all_json(directory):
    if not os.path.exists(directory):
        return []

    results = []
    for root, _, files in os.walk(directory):
        for name in files:
            if name.lower().endswith(".json"):
                path = os.path.join(root, name)
                data = _read_json_file(path)
                if data is not None:
                    results.append(data)
    return results


def ensure_memory_dirs():
    os.makedirs(RAW_DIR, exist_ok=True)
    for category in RAW_CATEGORIES:
        os.makedirs(os.path.join(RAW_DIR, category), exist_ok=True)

    os.makedirs(EPISODIC_DIR, exist_ok=True)
    os.makedirs(SEMANTIC_DIR, exist_ok=True)
    for category in SEMANTIC_CATEGORIES:
        os.makedirs(os.path.join(SEMANTIC_DIR, category), exist_ok=True)

    os.makedirs(EMBEDDINGS_DIR, exist_ok=True)
    os.makedirs(INDEXES_DIR, exist_ok=True)
    os.makedirs(SUMMARIES_DIR, exist_ok=True)

    _migrate_memory_json()


def _migrate_memory_json():
    if os.path.exists(MIGRATION_MARKER):
        return

    if not os.path.exists("memory.json"):
        return

    try:
        with open("memory.json", "r", encoding="utf-8") as f:
            old_memory = json.load(f)
    except Exception:
        return

    if not isinstance(old_memory, list):
        return

    for entry in old_memory:
        content = entry.get("content")
        mem_type = entry.get("type", "general")
        tags = entry.get("tags", [])
        timestamp = entry.get("timestamp", _now_iso())
        metadata = {
            "source": "migration",
            "original_type": mem_type,
            "tags": tags,
        }

        if isinstance(mem_type, str) and mem_type.lower() in SEMANTIC_CATEGORIES:
            category = mem_type.lower()
            filename = _safe_filename(timestamp) + ".json"
            path = os.path.join(SEMANTIC_DIR, category, filename)
            data = {
                "layer": "semantic",
                "category": category,
                "timestamp": timestamp,
                "content": content,
                "metadata": metadata,
            }
            _write_json(path, data)
        else:
            filename = _safe_filename(timestamp) + ".json"
            path = os.path.join(RAW_DIR, "notes", filename)
            data = {
                "layer": "raw",
                "category": "notes",
                "timestamp": timestamp,
                "content": content,
                "metadata": metadata,
            }
            _write_json(path, data)

    with open(MIGRATION_MARKER, "w", encoding="utf-8") as marker:
        marker.write("migrated")


def add_raw_memory(category, content, metadata=None, timestamp=None):
    ensure_memory_dirs()
    if category not in RAW_CATEGORIES:
        category = "notes"

    timestamp = timestamp or _now_iso()
    filename = _safe_filename(timestamp) + ".json"
    path = os.path.join(RAW_DIR, category, filename)

    data = {
        "layer": "raw",
        "category": category,
        "timestamp": timestamp,
        "content": content,
        "metadata": metadata or {},
    }
    _write_json(path, data)
    return path


def add_episodic_memory(content, summary=None, metadata=None, timestamp=None):
    ensure_memory_dirs()
    timestamp = timestamp or _now_iso()
    date_part = timestamp.split("T")[0]
    year, month, day = date_part.split("-")
    folder = os.path.join(EPISODIC_DIR, year, month, day)
    os.makedirs(folder, exist_ok=True)

    filename = _safe_filename(timestamp) + ".json"
    path = os.path.join(folder, filename)

    data = {
        "layer": "episodic",
        "timestamp": timestamp,
        "summary": summary,
        "content": content,
        "metadata": metadata or {},
    }
    _write_json(path, data)
    return path


def add_semantic_memory(category, content, metadata=None, timestamp=None, key=None):
    ensure_memory_dirs()
    if category not in SEMANTIC_CATEGORIES:
        category = "preferences"

    timestamp = timestamp or _now_iso()
    filename = _safe_filename(key or timestamp) + ".json"
    path = os.path.join(SEMANTIC_DIR, category, filename)

    data = {
        "layer": "semantic",
        "category": category,
        "timestamp": timestamp,
        "content": content,
        "metadata": metadata or {},
    }
    _write_json(path, data)
    return path


def get_memory_context(scope="semantic"):
    ensure_memory_dirs()
    sections = []

    if scope in ("semantic", "all"):
        semantic_files = []
        for category in SEMANTIC_CATEGORIES:
            semantic_files.extend(_load_all_json(os.path.join(SEMANTIC_DIR, category)))

        if semantic_files:
            sections.append("Semantic memory:")
            for item in semantic_files:
                content = item.get("content")
                category = item.get("category", "unknown")
                timestamp = item.get("timestamp", "unknown")
                sections.append(f"- [{category}] {content} ({timestamp})")

    if scope == "all":
        raw_files = []
        for category in RAW_CATEGORIES:
            raw_files.extend(_load_all_json(os.path.join(RAW_DIR, category)))

        if raw_files:
            sections.append("Raw memory:")
            for item in raw_files:
                content = item.get("content")
                category = item.get("category", "unknown")
                sections.append(f"- [{category}] {content}")

        episodic_files = _load_all_json(EPISODIC_DIR)
        if episodic_files:
            sections.append("Episodic memory:")
            for item in episodic_files:
                summary = item.get("summary") or item.get("content")
                timestamp = item.get("timestamp", "unknown")
                sections.append(f"- {summary} ({timestamp})")

    if not sections:
        return "No memory available yet."
    return "\n".join(sections)


def retrieve_memory(query, scope="semantic"):
    ensure_memory_dirs()
    query_lower = str(query).lower()
    matches = []

    directories = []
    if scope in ("semantic", "all"):
        directories.extend(os.path.join(SEMANTIC_DIR, cat) for cat in SEMANTIC_CATEGORIES)
    if scope in ("raw", "all"):
        directories.extend(os.path.join(RAW_DIR, cat) for cat in RAW_CATEGORIES)
    if scope in ("episodic", "all"):
        directories.append(EPISODIC_DIR)

    for directory in directories:
        for item in _load_all_json(directory):
            content = item.get("content")
            summary = item.get("summary", "")
            text = f"{content} {summary}"
            if query_lower in str(text).lower():
                matches.append(item)

    return matches
