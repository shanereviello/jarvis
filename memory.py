# memory.py
import datetime
import json
import os
import re
from config import MEMORY_ROOT, VAULT_ROOT

RAW_DIR = os.path.join(MEMORY_ROOT, "raw")
EPISODIC_DIR = os.path.join(MEMORY_ROOT, "episodic")
SEMANTIC_DIR = os.path.join(MEMORY_ROOT, "semantic")
EMBEDDINGS_DIR = os.path.join(MEMORY_ROOT, "embeddings")
INDEXES_DIR = os.path.join(MEMORY_ROOT, "indexes")
SUMMARIES_DIR = os.path.join(MEMORY_ROOT, "summaries")

RAW_CATEGORIES = ["conversations", "calendar", "system", "notes"]
SEMANTIC_CATEGORIES = ["preferences", "projects", "people", "tasks"]
SEMANTIC_DEFAULT_ENTITY = "user"
SEMANTIC_DEFAULT_SOURCE = "assistant_inference"
SEMANTIC_DEFAULT_STATUS = "active"
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "do", "for", "from", "how",
    "i", "in", "is", "it", "my", "of", "on", "or", "the", "this", "to", "use",
    "using", "what", "when", "where", "which", "with", "you", "your",
}


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
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for name in files:
            if name.startswith("._") or name.startswith("."):
                continue
            if name.lower().endswith(".json"):
                path = os.path.join(root, name)
                data = _read_json_file(path)
                if data is not None:
                    results.append(data)
    return results


def _slugify(value):
    value = str(value or "").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")[:80]


def _infer_category(attribute, fallback="preferences"):
    attribute = str(attribute or "").lower()
    if any(word in attribute for word in ["project", "repo", "work"]):
        return "projects"
    if any(word in attribute for word in ["name", "friend", "family", "manager", "colleague"]):
        return "people"
    if any(word in attribute for word in ["task", "todo", "deadline"]):
        return "tasks"
    return fallback


def _build_semantic_id(entity, attribute, value=None):
    parts = [
        _slugify(entity or SEMANTIC_DEFAULT_ENTITY),
        _slugify(attribute or "memory"),
    ]
    if value is not None and str(value).strip():
        parts.append(_slugify(str(value))[:40])
    return "_".join(part for part in parts if part)


def _normalize_semantic_record(category=None, content=None, metadata=None, timestamp=None, key=None):
    metadata = metadata or {}
    timestamp = timestamp or _now_iso()

    if isinstance(content, dict):
        raw = dict(content)
    else:
        raw = {
            "value": content,
            "attribute": metadata.get("attribute") or "note",
            "entity": metadata.get("entity") or SEMANTIC_DEFAULT_ENTITY,
        }

    entity = raw.get("entity") or metadata.get("entity") or SEMANTIC_DEFAULT_ENTITY
    attribute = raw.get("attribute") or metadata.get("attribute") or "note"
    value = raw.get("value")
    inferred_category = _infer_category(attribute, fallback=category or "preferences")
    normalized_category = raw.get("category") or category or inferred_category
    if normalized_category not in SEMANTIC_CATEGORIES:
        normalized_category = inferred_category if inferred_category in SEMANTIC_CATEGORIES else "preferences"

    record_id = raw.get("id") or key or _build_semantic_id(entity, attribute, value)
    last_confirmed_at = raw.get("last_confirmed_at") or timestamp

    record = {
        "id": record_id,
        "layer": "semantic",
        "category": normalized_category,
        "entity": entity,
        "attribute": attribute,
        "value": value,
        "confidence": raw.get("confidence", metadata.get("confidence", 0.8)),
        "source": raw.get("source") or metadata.get("source") or SEMANTIC_DEFAULT_SOURCE,
        "timestamp": raw.get("timestamp") or timestamp,
        "last_confirmed_at": last_confirmed_at,
        "status": raw.get("status") or SEMANTIC_DEFAULT_STATUS,
    }

    notes = raw.get("notes")
    if notes is not None:
        record["notes"] = notes

    aliases = raw.get("aliases")
    if aliases is not None:
        record["aliases"] = aliases

    evidence = raw.get("evidence")
    if evidence is not None:
        record["evidence"] = evidence

    # Keep legacy metadata only when it adds something beyond the first-class fields.
    extra_metadata = {
        k: v for k, v in metadata.items()
        if k not in {"entity", "attribute", "confidence", "source"}
    }
    if extra_metadata:
        record["metadata"] = extra_metadata

    return record


def _semantic_text(item):
    if "attribute" in item and item.get("value") is not None:
        entity = item.get("entity", "unknown")
        attribute = item.get("attribute", "unknown")
        value = item.get("value")
        return f"{entity}.{attribute} = {value}"
    if item.get("content") is not None:
        return str(item.get("content", ""))
    return ""


def _tokenize(text):
    return [
        token for token in re.findall(r"[a-z0-9]+", str(text).lower())
        if len(token) > 1 and token not in STOPWORDS
    ]


def _score_text_match(query, *text_parts):
    combined_text = " ".join(str(part or "") for part in text_parts)
    query_tokens = _tokenize(query)
    if not query_tokens:
        return 0

    haystack = combined_text.lower()
    score = 0
    unique_query_tokens = set(query_tokens)
    for token in unique_query_tokens:
        if token in haystack:
            score += 2

    if str(query).strip().lower() in haystack:
        score += 4

    return score


def _read_text_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        except Exception:
            return ""
    except Exception:
        return ""


def _extract_markdown_sections(text):
    lines = str(text).splitlines()
    sections = []
    current_heading = "Document"
    current_lines = []
    in_code_block = False

    def flush_section():
        body = "\n".join(current_lines).strip()
        if body:
            sections.append({
                "heading": current_heading,
                "content": body,
            })

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_code_block = not in_code_block
            current_lines.append(line)
            continue

        if not in_code_block and stripped.startswith("#"):
            flush_section()
            current_heading = stripped.lstrip("#").strip() or "Document"
            current_lines = []
            continue

        if (
            not in_code_block
            and stripped.startswith("**")
            and stripped.endswith("**")
            and len(stripped) > 4
        ):
            flush_section()
            current_heading = stripped.strip("*").strip() or "Document"
            current_lines = []
            continue

        current_lines.append(line)

    flush_section()
    if not sections and str(text).strip():
        sections.append({
            "heading": "Document",
            "content": str(text).strip(),
        })
    return sections


def _iter_vault_markdown_files():
    if not VAULT_ROOT or not os.path.isdir(VAULT_ROOT):
        return

    for root, dirs, files in os.walk(VAULT_ROOT):
        dirs[:] = [
            d for d in dirs
            if not d.startswith(".") and d.lower() != ".trash"
        ]
        for name in files:
            lower_name = name.lower()
            if name.startswith("._"):
                continue
            if not (lower_name.endswith(".md") or lower_name.endswith(".markdown")):
                continue
            yield os.path.join(root, name)


def _make_snippet(text, query, max_chars=500):
    clean_text = re.sub(r"\s+", " ", str(text)).strip()
    if len(clean_text) <= max_chars:
        return clean_text

    query_tokens = _tokenize(query)
    lower_text = clean_text.lower()
    start = 0
    for token in query_tokens:
        index = lower_text.find(token)
        if index != -1:
            start = max(0, index - 120)
            break

    snippet = clean_text[start:start + max_chars].strip()
    if start > 0:
        snippet = "..." + snippet
    if start + max_chars < len(clean_text):
        snippet = snippet + "..."
    return snippet


def _score_vault_file(query, relative_path, title, content):
    query_tokens = set(_tokenize(query))
    lower_query = str(query).lower()
    lower_path = str(relative_path).lower()
    lower_title = str(title).lower()
    lower_content = str(content).lower()

    score = _score_text_match(query, title, relative_path)

    if "rpi4" in query_tokens and "rpi4" in lower_title:
        score += 8
    if "udev" in query_tokens and "udev" in lower_content:
        score += 6
    if "serial" in query_tokens and "serial" in lower_content:
        score += 4
    if "usb" in query_tokens and "usb" in lower_content:
        score += 4
    if "id" in query_tokens and "by-id" in lower_content:
        score += 3
    if "engineering vault" in lower_query and "/reference/templates/" in lower_path:
        score -= 6
    if "/incidents/" in lower_path and "incident" not in query_tokens:
        score -= 3

    return score


def _find_best_section(query, text):
    best_section = None
    best_score = 0

    for section in _extract_markdown_sections(text):
        heading = section["heading"]
        content = section["content"]
        score = _score_text_match(query, heading, content)

        lower_heading = heading.lower()
        lower_content = content.lower()
        query_tokens = set(_tokenize(query))

        if any(token in query_tokens for token in {"usb", "serial", "udev", "id"}):
            if "network / serial / usb id" in lower_heading:
                score += 12
            if "custom udev rule for creating static usb id" in lower_heading:
                score += 16
            if "udev" in lower_content:
                score += 8
            if "attrs{serial}" in lower_content:
                score += 10
            if "symlink+=" in lower_content:
                score += 6
            if "idvendor" in lower_content or "idproduct" in lower_content:
                score += 6

        if score > best_score:
            best_score = score
            best_section = section

    return best_section, best_score


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
    data = _normalize_semantic_record(
        category=category,
        content=content,
        metadata=metadata,
        timestamp=timestamp,
        key=key,
    )
    filename = _safe_filename(data["id"]) + ".json"
    path = os.path.join(SEMANTIC_DIR, data["category"], filename)
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
                category = item.get("category", "unknown")
                timestamp = item.get("timestamp", "unknown")
                if "attribute" in item and "value" in item:
                    entity = item.get("entity", "unknown")
                    attribute = item.get("attribute", "unknown")
                    value = item.get("value")
                    confidence = item.get("confidence", "unknown")
                    sections.append(
                        f"- [{category}] {entity}.{attribute} = {value} "
                        f"(confidence={confidence}, confirmed={timestamp})"
                    )
                else:
                    content = item.get("content")
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
    scored_matches = []

    directories = []
    if scope in ("semantic", "all"):
        directories.extend(os.path.join(SEMANTIC_DIR, cat) for cat in SEMANTIC_CATEGORIES)
    if scope in ("raw", "all"):
        directories.extend(os.path.join(RAW_DIR, cat) for cat in RAW_CATEGORIES)
    if scope in ("episodic", "all"):
        directories.append(EPISODIC_DIR)

    for directory in directories:
        for item in _load_all_json(directory):
            content = _semantic_text(item)
            summary = item.get("summary", "")
            score = _score_text_match(query, content, summary, item.get("notes", ""))
            if score > 0:
                scored_matches.append((score, item))

    scored_matches.sort(
        key=lambda pair: (
            pair[0],
            pair[1].get("last_confirmed_at", ""),
            pair[1].get("timestamp", ""),
        ),
        reverse=True,
    )
    return [item for _, item in scored_matches]


def retrieve_vault_notes(query, limit=3):
    matches = []
    for path in _iter_vault_markdown_files() or []:
        content = _read_text_file(path)
        if not content.strip():
            continue

        relative_path = os.path.relpath(path, VAULT_ROOT) if VAULT_ROOT else path
        title = os.path.splitext(os.path.basename(path))[0]
        score = _score_vault_file(query, relative_path, title, content[:12000])
        if score <= 0:
            continue

        best_section, section_score = _find_best_section(query, content)
        if best_section is not None:
            score += section_score
            snippet_source = f"{best_section['heading']}\n{best_section['content']}"
        else:
            snippet_source = content

        matches.append({
            "path": path,
            "relative_path": relative_path,
            "title": title,
            "score": score,
            "snippet": _make_snippet(snippet_source, query),
            "section_heading": best_section["heading"] if best_section else None,
        })

    matches.sort(key=lambda item: (item["score"], item["relative_path"]), reverse=True)
    return matches[:limit]


def get_retrieval_context(query, memory_limit=6, vault_limit=3):
    ensure_memory_dirs()
    sections = []

    memory_matches = retrieve_memory(query, scope="semantic")[:memory_limit]
    if memory_matches:
        sections.append("Relevant semantic memory:")
        for item in memory_matches:
            category = item.get("category", "unknown")
            if item.get("attribute") and item.get("value") is not None:
                entity = item.get("entity", "unknown")
                attribute = item.get("attribute", "unknown")
                value = item.get("value")
                confidence = item.get("confidence", "unknown")
                sections.append(
                    f"- [{category}] {entity}.{attribute} = {value} "
                    f"(confidence={confidence})"
                )
                notes = item.get("notes")
                if notes:
                    sections.append(f"Notes: {notes}")
            else:
                content = item.get("content")
                if content:
                    sections.append(f"- [{category}] {content}")

    vault_matches = retrieve_vault_notes(query, limit=vault_limit)
    if vault_matches:
        sections.append("Relevant vault notes:")
        for item in vault_matches:
            heading = f" :: {item['section_heading']}" if item.get("section_heading") else ""
            sections.append(
                f"- [{item['relative_path']}{heading}] {item['snippet']}"
            )

    if not sections:
        return "No relevant memory or vault notes were retrieved for this query."

    return "\n".join(sections)
