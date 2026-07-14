from __future__ import annotations

import argparse
import json

from psycopg2.extras import RealDictCursor

from app.services.engineering_db import get_db_connection


def _run_lookup(
    cable_assy_id: str,
    component: str | None,
    jack: str | None,
) -> dict:
    sql = """
    SELECT
        wire_id,
        cable_assy_id,
        component_a,
        jack_a,
        component_b,
        jack_b,
        wire_purpose
    FROM wire_list
    WHERE cable_assy_id = %s
      AND (
        (%s IS NULL OR %s IS NULL)
        OR (component_a = %s AND jack_a = %s)
        OR (component_b = %s AND jack_b = %s)
      )
    ORDER BY wire_id;
    """

    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            sql,
            (
                cable_assy_id,
                component,
                jack,
                component,
                jack,
                component,
                jack,
            ),
        )
        rows = cur.fetchall()
        cur.close()
    finally:
        conn.close()

    return {
        "ok": True,
        "cable_assy_id": cable_assy_id,
        "component": component,
        "jack": jack,
        "count": len(rows),
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inspect exact wire_list rows for a cable assembly and optional endpoint."
    )
    parser.add_argument("cable_assy_id", help="Cable assembly ID, for example W001.")
    parser.add_argument("--component", help="Endpoint component label, for example A2.")
    parser.add_argument("--jack", help="Endpoint jack label, for example J1P10.")
    args = parser.parse_args()

    result = _run_lookup(args.cable_assy_id, args.component, args.jack)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
