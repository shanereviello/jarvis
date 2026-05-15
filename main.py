import datetime
import json
import os
import re
import shutil
import subprocess

from openai import OpenAI

from config import JARVIS_VAULT_ROOT, OPENAI_API_KEY
from memory import (
    add_episodic_memory,
    add_raw_memory,
    add_semantic_memory,
    append_session_message,
    compact_active_session,
    ensure_memory_dirs,
    get_active_session,
    get_memory_context,
    get_session_prompt_messages,
    remember_session_file,
    update_session_fact,
)
from tools.calendar import create_calendar_event

client = OpenAI(api_key=OPENAI_API_KEY)

ACTION_SYSTEM_PROMPT = """
You are a personal AI assistant.

You can store memory and create calendar events.

Only return tool JSON for an explicit tool action. Do not answer normal questions here.

If the user provides important personal info or asks you to remember something, respond ONLY in JSON:
{
  "action": "store_memory",
  "memory_layer": "semantic|episodic|raw",
  "category": "preferences|projects|people|tasks|conversations|calendar|system|notes",
  "content": "...",
  "summary": "..."
}

If the user asks to schedule something, respond ONLY in JSON:
{
  "action": "create_calendar_event",
  "title": "...",
  "datetime": "Month Day Year HH:MM AM/PM"
}

Do not include any extra text when returning JSON.
"""

PLANNER_SYSTEM_PROMPT = """
You are a routing and retrieval planner for a personal AI agent.

Return only valid JSON with this exact shape:
{
  "intent": "answer_general|retrieve_from_vault|save_memory|forget_memory|calendar_action|unknown",
  "memory_action": "none|save|forget",
  "sources_to_search": ["engineering_vault"],
  "entities": ["..."],
  "search_queries": ["..."],
  "original_user_question": "..."
}

Rules:
- Only classify as save_memory if the user explicitly asks to remember, save, store, note, or persist information.
- Questions about notes, files, YAML, markdown, configuration, Obsidian, NAS, or the engineering vault are retrieval questions.
- Do not answer the user.
- Do not invent tool actions.
"""

ANSWER_SYSTEM_PROMPT = """
You are a personal AI assistant.

Answer the user's question directly and clearly.
Use retrieved engineering vault context when provided.
If the vault context is incomplete or ambiguous, say so plainly instead of guessing.
Do not claim you searched files unless context is actually provided to you.
Only return JSON if you are explicitly asked to perform a tool action, which is not the case in this answering step.
"""

MEMORY_PATTERNS = [
    r"\bremember that\b",
    r"\bremember this\b",
    r"\bsave this\b",
    r"\bstore this\b",
    r"\bnote that\b",
    r"\bdon't forget\b",
    r"\bdo not forget\b",
    r"\bfrom now on\b",
]

CALENDAR_PATTERNS = [
    r"\bschedule\b",
    r"\bcalendar\b",
    r"\bset up (a |an )?(meeting|event|appointment|reminder)\b",
    r"\bbook\b.*\b(meeting|event|appointment)\b",
]

VAULT_PATTERNS = [
    r"\bengineering vault\b",
    r"\bfrom the vault\b",
    r"\bvault\b",
    r"\bobsidian\b",
    r"\bnote titled\b",
]


def classify_intent_locally(user_input):
    text = user_input.strip().lower()

    if any(re.search(pattern, text) for pattern in MEMORY_PATTERNS):
        return "save_memory"

    if any(re.search(pattern, text) for pattern in CALENDAR_PATTERNS):
        return "calendar_action"

    if any(re.search(pattern, text) for pattern in VAULT_PATTERNS):
        return "retrieve_from_vault"

    return "answer_general"


def parse_json_object(text):
    text = (text or "").strip()
    if not text:
        return None

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None

    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return None


def complete_chat(messages, json_mode=False):
    kwargs = {
        "model": "gpt-4o-mini",
        "messages": messages,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    response = client.chat.completions.create(**kwargs)
    return response.choices[0].message.content.strip()


def build_action_messages(user_input, today, memory_context, session_messages):
    return [
        {"role": "system", "content": ACTION_SYSTEM_PROMPT},
        {"role": "system", "content": f"Today's date is {today}"},
        {"role": "system", "content": memory_context},
        *session_messages,
        {"role": "user", "content": user_input},
    ]


def build_planner_messages(user_input, today, session_messages):
    return [
        {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
        {"role": "system", "content": f"Today's date is {today}"},
        *session_messages,
        {"role": "user", "content": user_input},
    ]


def build_answer_messages(user_input, today, memory_context, session_messages, vault_context="", plan=None):
    messages = [
        {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
        {"role": "system", "content": f"Today's date is {today}"},
        {"role": "system", "content": memory_context},
    ]

    if plan:
        messages.append({
            "role": "system",
            "content": "Planner output:\n" + json.dumps(plan, indent=2),
        })

    if vault_context:
        messages.append({
            "role": "system",
            "content": "Use this retrieved engineering vault context to answer the question. If the context is incomplete, say so plainly.\n\n"
            + vault_context,
        })
    else:
        messages.append({
            "role": "system",
            "content": "No retrieved vault context is available for this turn. Answer from available context only, and be explicit if you are uncertain.",
        })

    messages.extend(session_messages)
    messages.append({"role": "user", "content": user_input})
    return messages


def create_query_plan(user_input, today, session_messages):
    fallback_plan = {
        "intent": "answer_general",
        "memory_action": "none",
        "sources_to_search": [],
        "entities": [],
        "search_queries": [],
        "original_user_question": user_input,
    }

    reply = complete_chat(
        build_planner_messages(user_input, today, session_messages),
        json_mode=True,
    )
    data = parse_json_object(reply)
    if not isinstance(data, dict):
        return fallback_plan

    plan = dict(fallback_plan)
    plan.update(data)
    if not isinstance(plan.get("sources_to_search"), list):
        plan["sources_to_search"] = []
    if not isinstance(plan.get("entities"), list):
        plan["entities"] = []
    if not isinstance(plan.get("search_queries"), list):
        plan["search_queries"] = []
    if not plan.get("original_user_question"):
        plan["original_user_question"] = user_input
    return plan


def normalize_text(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()


def list_vault_files():
    if not JARVIS_VAULT_ROOT or not os.path.isdir(JARVIS_VAULT_ROOT):
        return []

    rg_path = shutil.which("rg")
    if rg_path:
        result = subprocess.run(
            [rg_path, "--files", JARVIS_VAULT_ROOT],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return [
                line.strip()
                for line in result.stdout.splitlines()
                if line.strip() and not os.path.basename(line.strip()).startswith("._")
            ]

    paths = []
    for root, _, files in os.walk(JARVIS_VAULT_ROOT):
        for name in files:
            if name.startswith("._"):
                continue
            paths.append(os.path.join(root, name))
    return paths


def extract_note_title_candidates(user_input, plan=None):
    candidates = []
    text = user_input.strip()

    patterns = [
        r"note titled\s+['\"]?(.+?)['\"]?(?:\s+then|\s+with|\s+that|\s+and|$)",
        r"file titled\s+['\"]?(.+?)['\"]?(?:\s+then|\s+with|\s+that|\s+and|$)",
        r"look for\s+(?:a\s+)?note\s+(?:called|named)\s+['\"]?(.+?)['\"]?(?:\s+then|\s+with|\s+that|\s+and|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            candidates.append(match.group(1).strip(" .?\"'"))

    if "realsense camera" in text.lower():
        candidates.append("Intel Realsense Camera")
        candidates.append("Intel Realsense D455 Camera")

    if isinstance(plan, dict):
        for entity in plan.get("entities", []):
            entity = str(entity).strip()
            if entity:
                candidates.append(entity)

    unique = []
    seen = set()
    for candidate in candidates:
        key = normalize_text(candidate)
        if key and key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


def find_vault_note_by_title(candidates):
    if not JARVIS_VAULT_ROOT or not candidates:
        return None

    paths = list_vault_files()
    if not paths:
        return None
    normalized = []
    for path in paths:
        name = path.rsplit("/", 1)[-1]
        stem = re.sub(r"\.[^.]+$", "", name)
        normalized.append((path, normalize_text(stem)))

    for candidate in candidates:
        wanted = normalize_text(candidate)
        for path, stem in normalized:
            if stem == wanted:
                return path

    for candidate in candidates:
        wanted = normalize_text(candidate)
        for path, stem in normalized:
            if wanted and wanted in stem:
                return path

    return None


def extract_yaml_section(text):
    patterns = [
        r"\*\*YAML.*?\*\*\s*~~~\s*(.*?)\s*~~~",
        r"#+\s+.*yaml.*?\n\s*~~~\s*(.*?)\s*~~~",
        r"~~~\s*(.*?)\s*~~~",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            block = match.group(1).strip()
            if ":" in block:
                return block
    return ""


def get_session_vault_file(user_input):
    text = user_input.lower()
    if not any(phrase in text for phrase in ["that file", "that note", "this file", "this note", "the file", "the note"]):
        return None

    session = get_active_session()
    path = session.get("active_facts", {}).get("current_vault_file")
    if path and not os.path.basename(path).startswith("._"):
        return path
    return None


def load_note_context(note_path, want_yaml=False, include_full_file=False, max_chars=30000):
    try:
        with open(note_path, "r", encoding="utf-8", errors="replace") as handle:
            text = handle.read()
    except Exception:
        return ""

    if include_full_file:
        if want_yaml:
            yaml_block = extract_yaml_section(text)
            if yaml_block:
                return (
                    f"Matched note: {note_path}\n\n"
                    f"YAML section:\n{yaml_block}\n\n"
                    f"Full file contents:\n{text[:max_chars]}"
                )
        return f"Matched note: {note_path}\n\nFull file contents:\n{text[:max_chars]}"

    if want_yaml:
        yaml_block = extract_yaml_section(text)
        if yaml_block:
            return f"Matched note: {note_path}\n\nYAML section:\n{yaml_block}"

    return f"Matched note: {note_path}\n\n{text[:max_chars]}"


def search_vault_with_python(queries, limit=20):
    snippets = []
    seen = set()
    files = [
        path for path in list_vault_files()
        if path.lower().endswith((".md", ".yaml", ".yml", ".json"))
    ]

    for query in queries[:6]:
        terms = [term.lower() for term in re.findall(r"[A-Za-z0-9_.-]+", query) if len(term) > 2]
        if not terms:
            continue

        for path in files:
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                    lines = handle.readlines()
            except OSError:
                continue

            lowered = [line.lower() for line in lines]
            for idx, line in enumerate(lowered):
                if not any(term in line for term in terms):
                    continue

                start = max(0, idx - 2)
                end = min(len(lines), idx + 3)
                block = "".join(lines[start:end]).strip()
                snippet = f"{path}:{idx + 1}\n{block}"
                if snippet in seen:
                    continue
                seen.add(snippet)
                snippets.append(snippet)
                if len(snippets) >= limit:
                    return "\n\n".join(snippets)

    return "\n\n".join(snippets)


def search_vault_context(queries, note_titles=None, want_yaml=False, prefer_full_note=False, user_input="", limit=20):
    if not JARVIS_VAULT_ROOT:
        return "", None

    if isinstance(queries, str):
        queries = [queries]

    queries = [str(query).strip() for query in (queries or []) if str(query).strip()]
    note_path = find_vault_note_by_title(note_titles or [])
    if not note_path:
        note_path = get_session_vault_file(user_input)
    if note_path:
        context = load_note_context(
            note_path,
            want_yaml=want_yaml,
            include_full_file=prefer_full_note,
        )
        return context, note_path

    if not queries:
        return "", None

    rg_path = shutil.which("rg")
    if not rg_path:
        return search_vault_with_python(queries, limit=limit), None

    snippets = []
    seen = set()

    for query in queries[:6]:
        terms = [term for term in re.findall(r"[A-Za-z0-9_.-]+", query) if len(term) > 2]
        if not terms:
            continue

        pattern = "|".join(dict.fromkeys(terms[:8]))
        cmd = [
            rg_path,
            "-n",
            "-i",
            "-C",
            "2",
            "--glob",
            "*.md",
            "--glob",
            "*.yaml",
            "--glob",
            "*.yml",
            "--glob",
            "*.json",
            pattern,
            JARVIS_VAULT_ROOT,
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        except FileNotFoundError:
            return ""

        if result.returncode not in (0, 1):
            continue

        for line in result.stdout.splitlines():
            line = line.strip()
            if not line or line in seen:
                continue
            seen.add(line)
            snippets.append(line)
            if len(snippets) >= limit * 8:
                return "\n".join(snippets[: limit * 8]), None

    return "\n".join(snippets[: limit * 8]), None


def execute_action(data, user_input):
    action = data.get("action")

    if action == "store_memory":
        layer = data.get("memory_layer", "semantic")
        category = data.get("category", "notes")
        content = data.get("content", "")
        summary = data.get("summary")
        metadata = {
            "source": "assistant",
            "user_input": user_input,
        }

        if layer == "raw":
            add_raw_memory(
                category,
                {
                    "content": content,
                    "summary": summary,
                },
                metadata=metadata,
            )
        elif layer == "episodic":
            add_episodic_memory(
                {
                    "user_input": user_input,
                    "content": content,
                },
                summary=summary,
                metadata=metadata,
            )
        else:
            add_semantic_memory(category, content, metadata=metadata)

        add_episodic_memory(
            {
                "event": "memory_store",
                "layer": layer,
                "category": category,
                "content": content,
            },
            summary=f"Stored memory in {layer}/{category}",
            metadata={"source": "assistant_action"},
        )
        return "Got it, I'll remember that."

    if action == "create_calendar_event":
        result = create_calendar_event(
            data.get("title", ""),
            data.get("datetime", ""),
        )
        add_episodic_memory(
            {
                "event": "calendar_event",
                "title": data.get("title", ""),
                "datetime": data.get("datetime", ""),
            },
            summary="Created a calendar event",
            metadata={"source": "assistant_action"},
        )
        return result

    return None


def ask_agent(user_input):
    ensure_memory_dirs()
    session_messages = get_session_prompt_messages()
    local_intent = classify_intent_locally(user_input)
    today = datetime.datetime.now().strftime("%B %d %Y")
    memory_context = get_memory_context("semantic")

    append_session_message("user", user_input)
    add_raw_memory(
        "conversations",
        {
            "role": "user",
            "content": user_input,
            "timestamp": datetime.datetime.now().isoformat(),
        },
    )

    if local_intent in {"save_memory", "calendar_action"}:
        action_reply = complete_chat(
            build_action_messages(
                user_input=user_input,
                today=today,
                memory_context=memory_context,
                session_messages=session_messages,
            ),
            json_mode=True,
        )
        data = parse_json_object(action_reply)
        final_reply = execute_action(data or {}, user_input) or action_reply
    else:
        plan = create_query_plan(
            user_input=user_input,
            today=today,
            session_messages=session_messages,
        )
        should_search_vault = local_intent == "retrieve_from_vault" or plan.get("intent") == "retrieve_from_vault"
        if plan.get("sources_to_search"):
            should_search_vault = should_search_vault or "engineering_vault" in plan.get("sources_to_search", [])

        vault_context = ""
        matched_note_path = None
        if should_search_vault:
            search_queries = plan.get("search_queries") or [user_input]
            note_titles = extract_note_title_candidates(user_input, plan=plan)
            want_yaml = "yaml" in user_input.lower() or "config" in user_input.lower()
            prefer_full_note = bool(note_titles) or any(
                phrase in user_input.lower()
                for phrase in ["that file", "that note", "this file", "this note"]
            )
            vault_context, matched_note_path = search_vault_context(
                search_queries,
                note_titles=note_titles,
                want_yaml=want_yaml,
                prefer_full_note=prefer_full_note,
                user_input=user_input,
            )
            if matched_note_path:
                remember_session_file(matched_note_path)
                update_session_fact("current_vault_file", matched_note_path)
                session_messages = get_session_prompt_messages()

        final_reply = complete_chat(
            build_answer_messages(
                user_input=user_input,
                today=today,
                memory_context=memory_context,
                session_messages=session_messages,
                vault_context=vault_context,
                plan=plan,
            )
        )

    append_session_message("assistant", final_reply)
    compact_active_session()
    add_raw_memory(
        "conversations",
        {
            "role": "assistant",
            "content": final_reply,
            "timestamp": datetime.datetime.now().isoformat(),
        },
    )

    add_episodic_memory(
        {
            "user_input": user_input,
            "assistant_response": final_reply,
        },
        summary="Standard interaction recorded",
        metadata={"source": "conversation"},
    )

    return final_reply


if __name__ == "__main__":
    ensure_memory_dirs()
    while True:
        try:
            user_input = input("You: ")
            reply = ask_agent(user_input)
            print("Agent:", reply)
        except KeyboardInterrupt:
            print("\nExiting...")
            break
