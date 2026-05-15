import json
import re
import datetime
from openai import OpenAI
from config import OPENAI_API_KEY
from memory import (
    ensure_memory_dirs,
    add_raw_memory,
    add_episodic_memory,
    add_semantic_memory,
    get_retrieval_context,
)
from tools.calendar import create_calendar_event

client = OpenAI(api_key=OPENAI_API_KEY)

SYSTEM_PROMPT = """
You are a personal AI assistant.

You can store memory and create calendar events.

Use semantic memory when answering user questions about stable preferences, people, projects, or tasks.
Use episodic memory to log what happened during a session or an interaction.
Use raw memory as a black box recorder for conversation history and system events.

Return normal natural-language answers by default.

Only respond ONLY in JSON for memory storage when the user explicitly asks you to remember, save, store, log, or note something for later, or clearly provides personal/project information with the clear intent that it should be remembered.

Do not store memory when the user is asking a normal question, even if the answer is based on memory or vault notes.

If you should store memory, respond ONLY in JSON:
{
  "action": "store_memory",
  "memory_layer": "semantic|episodic|raw",
  "category": "preferences|projects|people|tasks|conversations|calendar|system|notes",
  "content": "...",
  "summary": "...",
  "entity": "user|person_name|project_name",
  "attribute": "favorite_editor|timezone|preferred_workflow",
  "value": "actual remembered value",
  "confidence": 0.0,
  "source": "user_statement|assistant_inference",
  "status": "active|deprecated|deleted"
}

For semantic memory:
- Prefer atomic facts over long summaries.
- Put the real fact in "value".
- Use snake_case for "attribute".
- Use "source": "user_statement" when the user explicitly states it.
- Keep "content" as a short human-readable sentence.

Only respond ONLY in JSON for calendar creation when the user explicitly asks to schedule or create a calendar event.

If you should create a calendar event, respond ONLY in JSON:
{
  "action": "create_calendar_event",
  "title": "...",
  "datetime": "Month Day Year HH:MM AM/PM"
}

Do not include any extra text when returning JSON.
"""


def _parse_action_response(reply):
    text = str(reply or "").strip()
    if not (text.startswith("{") and text.endswith("}")):
        return None

    try:
        data = json.loads(text)
    except Exception:
        return None

    if not isinstance(data, dict):
        return None

    action = data.get("action")
    if action not in {"store_memory", "create_calendar_event"}:
        return None

    return data


def ask_agent(user_input):
    ensure_memory_dirs()
    add_raw_memory("conversations", {
        "role": "user",
        "content": user_input,
        "timestamp": datetime.datetime.now().isoformat(),
    })

    memory_context = get_retrieval_context(user_input)
    today = datetime.datetime.now().strftime("%B %d %Y")

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "system", "content": f"Today's date is {today}"},
            {
                "role": "system",
                "content": (
                    "Use retrieved context only when it is relevant to the user's request. "
                    "Do not assume unrelated memory or vault notes apply.\n\n"
                    f"{memory_context}"
                ),
            },
            {"role": "user", "content": user_input},
        ]
    )

    reply = response.choices[0].message.content.strip()
    add_raw_memory("conversations", {
        "role": "assistant",
        "content": reply,
        "timestamp": datetime.datetime.now().isoformat(),
    })

    data = _parse_action_response(reply)
    if data:
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
                add_raw_memory(category, {
                    "content": content,
                    "summary": summary,
                }, metadata=metadata)
            elif layer == "episodic":
                add_episodic_memory(
                    {
                        "user_input": user_input,
                        "content": content,
                        "assistant_response": reply,
                    },
                    summary=summary,
                    metadata=metadata,
                )
            else:
                semantic_record = {
                    "id": data.get("id"),
                    "category": category,
                    "entity": data.get("entity", "user"),
                    "attribute": data.get("attribute"),
                    "value": data.get("value", content),
                    "confidence": data.get("confidence", 0.9),
                    "source": data.get("source", "assistant_inference"),
                    "timestamp": data.get("timestamp"),
                    "last_confirmed_at": data.get("last_confirmed_at"),
                    "status": data.get("status", "active"),
                    "notes": content,
                }
                add_semantic_memory(category, semantic_record, metadata=metadata)

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

    add_episodic_memory(
        {
            "user_input": user_input,
            "assistant_response": reply,
        },
        summary="Standard interaction recorded",
        metadata={"source": "conversation"},
    )

    return reply


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
