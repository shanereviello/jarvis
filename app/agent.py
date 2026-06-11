from agents import Agent, Runner

from app.tools.db_retrieval import search_components_database
from app.tools.note_search import read_note


agent = Agent(
    name="Jarvis Component Retrieval Agent",
    instructions="""
You are Jarvis, Shane's engineering database retrieval assistant.

Use search_components_database when the user asks about robot parts,
components, sensors, controllers, compute hardware, enclosures, or hardware
configuration.

Use read_note when a result includes a notes_path and more detail is needed.

Do not invent project-specific details.
If the database returns no result, say that clearly.
If the database returns close matches, explain which match seems most likely.
""",
    tools=[search_components_database, read_note],
)


async def ask_jarvis(query: str) -> str:
    result = await Runner.run(agent, query)
    return result.final_output

