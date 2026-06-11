import psycopg2
from agents import function_tool

from app.config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER


def get_db_connection():
    return psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
    )


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
    params = (query, wildcard, query)

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as exc:
        return f"Database error: {exc}"

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

