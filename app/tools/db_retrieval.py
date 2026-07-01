import psycopg2

from app.config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER


def get_db_connection():
    return psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
    )


def search_components_records(query: str) -> dict:
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
        return {
            "ok": False,
            "query": query,
            "error": str(exc),
            "results": [],
        }

    results = [
        {
            "component_name": name,
            "notes_path": notes_path,
            "match_score": round(score, 3),
        }
        for name, notes_path, score in rows
    ]

    return {
        "ok": True,
        "query": query,
        "count": len(results),
        "results": results,
    }
