"""Local per-app OAuth administration; never prints credentials or callback codes."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sqlite3


def local(name):
    spec = importlib.util.spec_from_file_location('reporting_oauth_entry_' + name, Path(__file__).with_name(name + '.py'))
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value); return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['init', 'status', 'begin', 'refresh', 'recover-refresh',
                                            'reconcile-identity', 'revoke', 'serve-callback-only'])
    parser.add_argument('--configuration', required=True, type=Path)
    parser.add_argument('--state', required=True, type=Path)
    parser.add_argument('--authorization-file', type=Path)
    parser.add_argument('--port', type=int, default=8767)
    args = parser.parse_args(argv)
    try:
        oauth = local('linear_oauth')
        selected = oauth.core.decode(oauth.core.private_file(args.configuration))
        vault = oauth.Vault(args.state, selected, create=args.operation == 'init')
        if args.operation in ('init', 'status'): result = vault.status()
        elif args.operation == 'begin':
            path = args.authorization_file
            if path is None or not path.is_absolute() or path.resolve(strict=False) != path:
                raise ValueError('private exclusive authorization output required')
            # Reserve output before consuming state. A failed write retains pending
            # custody; do not silently generate a different installation request.
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'wb') as stream:
                start = vault.begin(); stream.write(oauth.core.encoded(start)); stream.flush(); os.fsync(stream.fileno())
            result = dict(agent=selected['agent'], authorization_file=str(path), expires_at=start['expires_at'])
        elif args.operation in ('refresh', 'recover-refresh'):
            result = vault.refresh(recover=args.operation == 'recover-refresh')
        elif args.operation == 'reconcile-identity': result = vault.reconcile_identity()
        elif args.operation == 'revoke': result = vault.revoke()
        else:
            if not 1024 <= args.port <= 65535: raise ValueError('unprivileged port required')
            import uvicorn
            uvicorn.run(local('linear_http').create_app(oauth_vaults={selected['agent']: vault}),
                        host='127.0.0.1', port=args.port, access_log=False, log_level='warning')
            return
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    except (ValueError, KeyError, TypeError, AttributeError, OSError, sqlite3.Error):
        parser.exit(1, 'Linear OAuth operation refused or uncertain; preserve private custody and consult status.\n')


if __name__ == '__main__': main()
