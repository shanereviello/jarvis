from __future__ import annotations

import argparse
import json

from psycopg2 import sql
from psycopg2.extras import RealDictCursor

from app.services.engineering_db import get_db_connection, get_engineering_db_schema_catalog


def _run_scan(query: str, table_filter: set[str] | None) -> dict:
    catalog = get_engineering_db_schema_catalog()
    if not catalog.ok:
        return catalog.to_dict()

    wildcard = f"%{query}%"
    payload: dict[str, object] = {
        "ok": True,
        "query": query,
        "matches": [],
    }
    matches: list[dict[str, object]] = []

    conn = get_db_connection()
    try:
        for table in catalog.tables:
            if table_filter and table.table_name not in table_filter:
                continue
            if not table.searchable_columns:
                continue

            for column_name in table.searchable_columns:
                query_sql = sql.SQL(
                    "SELECT {column}::text AS matched_value "
                    "FROM {table} "
                    "WHERE {column}::text ILIKE %s "
                    "LIMIT 5"
                ).format(
                    column=sql.Identifier(column_name),
                    table=sql.Identifier(catalog.schema_name, table.table_name),
                )
                cur = conn.cursor(cursor_factory=RealDictCursor)
                cur.execute(query_sql, (wildcard,))
                rows = cur.fetchall()
                cur.close()

                if rows:
                    matches.append(
                        {
                            "table": table.table_name,
                            "column": column_name,
                            "sample_values": [row["matched_value"] for row in rows],
                        }
                    )
    finally:
        conn.close()

    payload["matches"] = matches
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scan every searchable engineering DB text column with raw ILIKE matching."
    )
    parser.add_argument("query", help="Raw text to search for, such as rpi4b.")
    parser.add_argument(
        "--tables",
        nargs="*",
        default=None,
        help="Optional table allowlist.",
    )
    args = parser.parse_args()

    table_filter = set(args.tables) if args.tables else None
    result = _run_scan(args.query, table_filter)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
