from __future__ import annotations

import argparse
import json

from app.services.engineering_db import engineering_db_connection_lookup


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the production engineering DB connection lookup service directly."
    )
    parser.add_argument("cable_assy_id", help="Cable assembly ID, for example W001.")
    parser.add_argument("--component", dest="endpoint_component", help="Endpoint component label, for example A2.")
    parser.add_argument("--jack", dest="endpoint_jack", help="Endpoint jack label, for example J1P10.")
    parser.add_argument(
        "--requested-field",
        dest="requested_fields",
        action="append",
        default=[],
        help="Field to emphasize in the output. Repeat as needed.",
    )
    parser.add_argument("--max-rows", type=int, default=50, help="Maximum rows to return.")
    args = parser.parse_args()

    result = engineering_db_connection_lookup(
        cable_assy_id=args.cable_assy_id,
        endpoint_component=args.endpoint_component,
        endpoint_jack=args.endpoint_jack,
        requested_fields=args.requested_fields,
        max_rows=args.max_rows,
    )
    print(json.dumps(result.to_dict(), indent=2))


if __name__ == "__main__":
    main()
