from __future__ import annotations

import argparse
import json

from app.services.engineering_db import retrieve_engineering_db_schema_context


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inspect how Jarvis narrows engineering DB tables for a query."
    )
    parser.add_argument("query", help="User query to score against the engineering DB schema.")
    parser.add_argument("--max-tables", type=int, default=8, help="Maximum suggested tables to return.")
    args = parser.parse_args()

    result = retrieve_engineering_db_schema_context(args.query, max_tables=args.max_tables)
    print(json.dumps(result.to_dict(), indent=2))


if __name__ == "__main__":
    main()
