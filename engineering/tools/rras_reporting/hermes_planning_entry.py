"""Run the separately configured private Jarvis planning bridge."""
import argparse
import importlib.util
from pathlib import Path
import signal
from contextlib import nullcontext


def local(name):
    spec=importlib.util.spec_from_file_location('hermes_planning_entry_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def run(config,scope_path,reader_token,bridge_token,*,state=None,creator_token=None):
    if not Path(scope_path).is_absolute():raise ValueError('absolute protected scope path required')
    if (state is None)!=(creator_token is None):raise ValueError('paired issue state and credential required')
    resolver=local('hermes_planning_scope').Resolver(scope_path)
    journal=local('hermes_planning_journal').open_journal(state) if state is not None else nullcontext(None)
    with journal as connection:
        server=local('hermes_planning_service').assemble(config,reader_token,bridge_token,resolver,
            creator_token=creator_token,connection=connection)
        previous=signal.getsignal(signal.SIGTERM)
        def terminate(_signum,_frame):
            signal.signal(signal.SIGTERM,signal.SIG_IGN)
            raise SystemExit(0)
        signal.signal(signal.SIGTERM,terminate)
        try:server.serve_forever(poll_interval=0.2)
        finally:
            try:server.server_close()
            finally:signal.signal(signal.SIGTERM,previous)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True);parser.add_argument('--scopes',required=True)
    parser.add_argument('--reader-token',required=True);parser.add_argument('--bridge-token',required=True)
    parser.add_argument('--state');parser.add_argument('--creator-token');parser.add_argument('--initialize',action='store_true')
    args=parser.parse_args()
    try:
        protected=local('protected_config')
        config=protected.decode(args.config,require_root=True,maximum=65536)
        if args.initialize:
            if not args.state:raise ValueError('new private issue state required')
            import json
            print(json.dumps(local('hermes_planning_journal').initialize(args.state),sort_keys=True));return
        reader=protected.read(args.reader_token,require_root=True,maximum=257).strip()
        bridge=protected.read(args.bridge_token,require_root=True,maximum=257).strip()
        creator=protected.read(args.creator_token,require_root=True,maximum=257).strip() if args.creator_token else None
        run(config,args.scopes,reader,bridge,state=args.state,creator_token=creator)
    except (ValueError,OSError,TypeError,KeyError):
        parser.exit(1,'Private Jarvis planning service refused; inspect protected configuration.\n')


if __name__=='__main__':main()
