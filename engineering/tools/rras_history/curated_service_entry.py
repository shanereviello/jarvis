"""Curated read service entry; only runtime ACL/socket writes, no publication route."""
import argparse
import importlib.util
import os
from pathlib import Path
import signal
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'vendor'))


def local(name):
    spec=importlib.util.spec_from_file_location('curated_service_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def serve(catalog,socket,policy,stopping):
    transport=local('unix');grants=transport.load_policy(policy)
    access=local('curated_read_access').Access(catalog,grants)
    # Container root can impersonate UIDs. No broader operator/owner grant may
    # exist on the endpoint made reachable inside Hermes.
    if 1000 in access.grants or os.getuid() in access.grants:raise ValueError('dedicated curated reader roles only')
    prod=local('production_entry')
    def bound(path):
        readers=[uid for uid,repositories in access.grants.items() if repositories]
        prod.set_acl(path.parent,readers,directory=True);prod.set_acl(path,readers,directory=False)
    with local('curated_read_unix').Server(socket,catalog,grants,on_bound=bound) as server:
        while not stopping():server.serve_once()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--account',default='995')
    parser.add_argument('--catalog',default='/var/lib/rras-curated-history/catalog')
    parser.add_argument('--socket',default='/run/rras-curated-history/read.sock')
    parser.add_argument('--policy',default='/etc/rras-curated-history/read-policy.json')
    args=parser.parse_args(argv);stopped=[False]
    def stop(*_):stopped[0]=True
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    try:
        prod=local('production_entry');prod.service_environment();prod.require_account(args.account)
        serve(args.catalog,args.socket,args.policy,lambda:stopped[0])
    except (ValueError,KeyError,TypeError,OSError,subprocess.SubprocessError):
        parser.exit(1,'Curated reader refused; preserve catalog, policy and socket evidence.\n')


if __name__=='__main__':main()
