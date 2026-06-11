import os
import asyncio
import psycopg2
from dotenv import load_dotenv
from agents import Agent, Runner, function_tool

load_dotenv()
PROJECT_PATH = os.getenv("PROJECT_PATH")


def get_db_connection():
    return psycopg2.connect(
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
    )

### TOOL TO SEARCH COMPONENTS DATABASE ###

@function_tool
def search_components_database(query: str) -> str:
    """
    Search the robot components database using fuzzy matching.

    Use this when the user asks about robot parts, components, sensors,
    controllers, compute hardware, enclosures, or related notes.

    Current known table:
    - components

    Current known searchable column:
    - name
    """

    sql = """
    SELECT
        name,
        notes,
        similarity(name, %s) AS score
    FROM components
    WHERE
        name ILIKE %s
        OR similarity(name, %s) > 0.20
    ORDER BY score DESC
    LIMIT 10;
    """

    wildcard = f"%{query}%"

    params = (
        query,
        wildcard,
        query,
    )

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        return f"Database error: {e}"

    if not rows:
        return "No matching components found."

    results = []

    for name, notes_path, score in rows:
        results.append(
            f"""
    component_name: {name}
    notes_path: {notes_path}
    match_score: {score:.3f}
    """
    )

    return "\n---\n".join(results)

### TOOL TO READ NOTES ###

@function_tool
def read_note(notes_path: str) -> str:
    """
    Read an engineering note from the local NAS/Obsidian vault.
    Use this after finding a component with a notes_path.
    """
    from pathlib import Path

    path = Path(PROJECT_PATH) / notes_path

    if not path.exists():
        return f"Note file not found: {notes_path}"

    return path.read_text(errors="ignore")[:8000]

### AGENT ###

agent = Agent(
    name="Jarvis Component Retrieval Agent",
    instructions="""
You are Jarvis, Shane's engineering database retrieval assistant.

Use search_components_database when the user asks about robot parts,
components, sensors, controllers, compute hardware, enclosures, or hardware
configuration.

Do not invent project-specific details.
If the database returns no result, say that clearly.
If the database returns close matches, explain which match seems most likely.
""",
    tools=[search_components_database, read_note],
)


async def main():
    print("Jarvis DB agent ready. Type 'exit' to quit.\n")

    while True:
        user_input = input("You: ")

        if user_input.lower() in ["exit", "quit"]:
            break

        result = await Runner.run(agent, user_input)
        print("\nJarvis:")
        print(result.final_output)
        print()


if __name__ == "__main__":
    asyncio.run(main())