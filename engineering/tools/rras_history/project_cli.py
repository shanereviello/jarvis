"""Explicit project requests/reads and owner-only migration. No browser writes.

Keep exact request files for retry. Replaying unchanged inputs recovers receipts;
never generate a fresh event key to repair a lost response.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import stat
from jsonschema import ValidationError


def local(name):
    spec = importlib.util.spec_from_file_location('project_cli_' + name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_file(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or
                info.st_uid != os.getuid() or info.st_mode & 0o077):
            raise ValueError('caller-owned private request file required')
        return local('contract').decode(stream.read(128 * 1024 + 1))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('migration-plan', 'migrate', 'submit', 'read'))
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument('--store')
    target.add_argument('--service-socket')
    parser.add_argument('--service-uid', type=int)
    parser.add_argument('--request', help='exact private project envelope or scoped query JSON')
    parser.add_argument('--expected-sha256', help='reviewed owner-only migration fingerprint')
    args = parser.parse_args(argv)
    try:
        if args.store:
            if args.service_uid is not None:
                raise ValueError('select one transport')
            projects = local('projects').Projects(local('store').Store(args.store))
            if args.operation == 'migration-plan':
                result = projects.migration_plan()
            elif args.operation == 'migrate':
                result = projects.migrate(args.expected_sha256)
            elif args.operation == 'submit':
                result = projects.submit(read_file(args.request))
            else:
                query = read_file(args.request)
                if set(query) != {'scope', 'query'}:
                    raise ValueError('exact scope and query required')
                result = projects.read(query['scope'], query['query'])
        else:
            if args.operation not in ('submit', 'read') or args.service_uid is None:
                raise ValueError('migration is local owner-only; service UID required')
            value = read_file(args.request)
            message = {'method': 'project_submit', 'request': value} if args.operation == 'submit' else {'method': 'project_read', **value}
            result = local('unix').call(args.service_socket, args.service_uid, message)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    except (ValueError, KeyError, TypeError, OSError, sqlite3.Error, ValidationError):
        parser.exit(1, 'Project operation refused; preserve exact requests, receipts and database.\n')


if __name__ == '__main__':
    main()
