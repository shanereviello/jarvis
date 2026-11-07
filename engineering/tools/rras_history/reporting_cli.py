"""Explicit reporting metadata reads/writes and owner-only reviewed migration."""
import argparse
import importlib.util
import json
from pathlib import Path
import sqlite3
from jsonschema import ValidationError


def local(name):
    spec = importlib.util.spec_from_file_location('reporting_cli_' + name, Path(__file__).with_name(name + '.py'))
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value); return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('migration-plan', 'migrate', 'submit', 'read'))
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument('--store'); target.add_argument('--service-socket')
    parser.add_argument('--service-uid', type=int); parser.add_argument('--request'); parser.add_argument('--expected-sha256')
    args = parser.parse_args(argv)
    try:
        value = None
        if args.operation in ('submit', 'read'):
            value = local('project_cli').read_file(args.request)
            if args.operation == 'submit': value = local('reporting_contract').validate(value)
            elif set(value) != {'scope', 'query'} or value['query'].get('view') != 'reporting':
                raise ValueError('exact scoped reporting query required')
        if args.store:
            if args.service_uid is not None: raise ValueError('select one transport')
            store = local('store').Store(args.store); reporting = local('reporting').Reporting(store)
            if args.operation == 'migration-plan': result = reporting.migration_plan()
            elif args.operation == 'migrate': result = reporting.migrate(args.expected_sha256)
            elif args.operation == 'submit': result = reporting.submit(value)
            else: result = local('projects').Projects(store).read(value['scope'], value['query'])
        else:
            if args.operation not in ('submit', 'read') or args.service_uid is None:
                raise ValueError('migration is local store-owner only')
            message = dict(method='reporting_submit', request=value) if args.operation == 'submit' else dict(method='project_read', **value)
            result = local('unix').call(args.service_socket, args.service_uid, message)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    except (ValueError, KeyError, TypeError, AttributeError, OSError, sqlite3.Error, ValidationError):
        parser.exit(1, 'Reporting operation refused; preserve exact requests, receipts and private custody.\n')


if __name__ == '__main__': main()
