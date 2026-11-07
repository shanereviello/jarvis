"""Explicit private Linear inbox administration. Not a model runner or installer."""
import argparse
import importlib.util
import json
from pathlib import Path
import sqlite3


def local(name):
    spec = importlib.util.spec_from_file_location('reporting_entry_' + name, Path(__file__).with_name(name + '.py'))
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value); return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['init', 'check', 'messages', 'bind', 'activity', 'serve-record-only'])
    parser.add_argument('--policy', type=Path, required=True)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--agent', choices=['jarvis', 'codex'])
    parser.add_argument('--session')
    parser.add_argument('--runtime-session')
    parser.add_argument('--key')
    parser.add_argument('--kind', choices=['thought', 'response', 'elicitation', 'error'])
    parser.add_argument('--body-file', type=Path)
    parser.add_argument('--after', type=int, default=0)
    parser.add_argument('--port', type=int, default=8766)
    args = parser.parse_args(argv)
    try:
        core = local('linear_agents')
        config = core.policy(core.decode(core.private_file(args.policy)))
        inbox = core.Inbox(args.state, config, create=args.operation == 'init')
        if args.operation in ('init', 'check'):
            result = dict(configured_agents=['jarvis', 'codex'], issue_count=len(config['issues']),
                state=str(inbox.root), execution_enabled=False, linear_connected=False)
        elif args.operation == 'messages': result = inbox.messages(args.agent, after=args.after)
        elif args.operation == 'bind': result = inbox.bind_runtime(args.agent, args.session, args.runtime_session)
        elif args.operation == 'activity':
            result = inbox.activity(args.agent, args.session, args.key, args.kind,
                core.private_file(args.body_file, core.MAX_TEXT).decode('utf-8'))
        else:
            if not 1024 <= args.port <= 65535: raise ValueError('unprivileged port required')
            import uvicorn
            uvicorn.run(local('linear_http').create_app(inbox), host='127.0.0.1', port=args.port,
                        access_log=False, log_level='warning')
            return
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    except (ValueError, KeyError, TypeError, AttributeError, OSError, sqlite3.Error):
        parser.exit(1, 'Linear inbox operation refused; preserve state and exact inputs.\n')


if __name__ == '__main__': main()
