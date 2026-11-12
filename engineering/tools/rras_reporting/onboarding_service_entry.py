"""Explicitly initialize or run the private, separately authorized planner."""
import argparse
from contextlib import contextmanager
import importlib.util
import os
from pathlib import Path
import signal
import sqlite3


def local(name):
    spec=importlib.util.spec_from_file_location('planning_service_entry_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def initialize(root):
    runtime=local('codex_runtime');root=Path(root)
    if not root.is_absolute() or root.resolve()!=root or root.exists():raise ValueError('new private planning state required')
    root.mkdir(mode=0o700,parents=False,exist_ok=False);runtime.private(root,True)
    path=root/'planning.sqlite3';fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600);os.close(fd)
    with sqlite3.connect(path) as db:local('onboarding_service').initialize_empty(db)
    return dict(initialized=True,models_started=0,listener_started=False)


def run(config,root,reader_token,bridge_token,creator_token=None):
    runtime=local('codex_runtime');root=runtime.private(root,True);path=runtime.private(root/'planning.sqlite3')
    if (type(config) is not dict or config.get('lock_path')!=str(root/'planning.lock') or
            config.get('runtime_policy',{}).get('peer_uid')==os.getuid()):
        raise ValueError('distinct native identity and private state lock required')
    @contextmanager
    def connection():
        runtime.private(path)
        db=sqlite3.connect(path,timeout=5);db.execute('PRAGMA synchronous=FULL');db.execute('PRAGMA foreign_keys=ON')
        try:yield db
        except BaseException:db.rollback();raise
        finally:db.close()
    if reader_token==bridge_token or (creator_token is not None and creator_token in (reader_token,bridge_token)):
        raise ValueError('distinct planning credentials required')
    service=local('onboarding_service').assemble(config,connection,reader_token,bridge_token,creator_token=creator_token)
    previous=signal.getsignal(signal.SIGTERM)
    def terminate(_signum,_frame):signal.signal(signal.SIGTERM,signal.SIG_IGN);raise SystemExit(0)
    signal.signal(signal.SIGTERM,terminate)
    try:
        acl=local('runtime_checkpoint_broker').acl_on_bound
        service.serve(lambda bound:acl(bound,config['runtime_policy']['peer_uid']))
    finally:
        try:service.close()
        finally:signal.signal(signal.SIGTERM,previous)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True);parser.add_argument('--state',required=True)
    parser.add_argument('--reader-token',required=True);parser.add_argument('--bridge-token',required=True)
    parser.add_argument('--creator-token')
    parser.add_argument('--initialize',action='store_true');args=parser.parse_args()
    try:
        protected=local('protected_config');config=protected.decode(args.config,require_root=True)
        if args.initialize:
            import json
            print(json.dumps(initialize(args.state),sort_keys=True));return
        reader=protected.read(args.reader_token,maximum=257,require_root=True).strip()
        bridge=protected.read(args.bridge_token,maximum=257,require_root=True).strip()
        creator=protected.read(args.creator_token,maximum=257,require_root=True).strip() if args.creator_token else None
        run(config,Path(args.state),reader,bridge,creator)
    except (ValueError,OSError,KeyError,TypeError,sqlite3.Error):parser.exit(1,'Private planning service refused; retain state for reconciliation.\n')


if __name__=='__main__':main()
