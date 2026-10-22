"""Explicit private local engineering records; not an installed service client."""
import argparse
import importlib.util
import json
import os
import stat
from pathlib import Path
import sqlite3
import sys
from jsonschema import ValidationError


def local(name):
    s = importlib.util.spec_from_file_location('engineering_' + name, Path(__file__).with_name(name + '.py'))
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for command in ('init', 'submit', 'history', 'document', 'outbox'):
        p = sub.add_parser(command); p.add_argument('--store', required=True)
        if command == 'submit': p.add_argument('--request', required=True)
        if command == 'history': p.add_argument('--work-id')
        if command in ('history', 'outbox'):
            p.add_argument('--offset', type=int, default=0); p.add_argument('--limit', type=int, default=100)
        if command == 'document':
            p.add_argument('--document-id', required=True); p.add_argument('--version', type=int)
    args = parser.parse_args(argv)
    try:
        store = local('store').Store(args.store, create=args.command == 'init')
        if args.command == 'init': result = {'initialized': True, 'authority_granted': False}
        elif args.command == 'submit':
            c = local('contract')
            fd = os.open(args.request, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, 'rb') as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > c.MAX_REQUEST:
                    raise ValueError('bounded regular request file required')
                raw = stream.read(c.MAX_REQUEST + 1)
            result = store.submit(c.decode(raw))
        elif args.command == 'history': result = store.history(args.work_id, offset=args.offset, limit=args.limit)
        elif args.command == 'outbox': result = store.pending(offset=args.offset, limit=args.limit)
        else:
            raw, _ = store.document(args.document_id, args.version)
            sys.stdout.buffer.write(raw); return
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    except (ValueError, KeyError, TypeError, OSError, sqlite3.Error, ValidationError):
        parser.exit(1, 'Local history operation refused; preserve existing records and inspect inputs.\n')


if __name__ == '__main__': main()
