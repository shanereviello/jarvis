from __future__ import annotations

import argparse
import json

from app.services.engineering_db import engineering_db_lookup


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the engineering DB lookup directly without going through n8n."
    )
    parser.add_argument("query", help="Lookup query.")
    parser.add_argument(
        "--tables",
        nargs="*",
        default=None,
        help="Optional candidate tables to force the lookup to search.",
    )
    parser.add_argument(
        "--requested-fields",
        nargs="*",
        default=None,
        help="Optional output fields to request, such as component_id name notes_path.",
    )
    parser.add_argument(
        "--entity-hint",
        default=None,
        help="Optional hint like component, interface, wire, cable, or gpio.",
    )
    parser.add_argument(
        "--follow-relationships",
        action="store_true",
        help="Include relationship context in the returned summaries.",
    )
    parser.add_argument("--max-tables", type=int, default=5)
    parser.add_argument("--max-rows-per-table", type=int, default=5)
    args = parser.parse_args()

    result = engineering_db_lookup(
        search_term=args.query,
        candidate_tables=args.tables,
        requested_fields=args.requested_fields,
        entity_hint=args.entity_hint,
        follow_relationships=args.follow_relationships,
        max_tables=args.max_tables,
        max_rows_per_table=args.max_rows_per_table,
    )
    print(json.dumps(result.to_dict(), indent=2))


if __name__ == "__main__":
    main()
