"""Unprivileged service entry with exact per-UID filesystem ACLs; no installer."""
import argparse
import importlib.util
import os
from pathlib import Path
import pwd
import signal
import sqlite3
import stat
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'vendor'))


def local(name):
    spec=importlib.util.spec_from_file_location('history_production_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def require_account(name):
    expected=int(name) if name.isdecimal() else pwd.getpwnam(name).pw_uid
    local('unix').uid(expected)
    if expected==1000:raise ValueError('interactive account cannot own service')
    if os.getuid()!=expected or os.geteuid()!=expected:raise ValueError('dedicated service identity differs')


def service_environment():
    # Do not inherit manager-added provider/client credentials into the daemon.
    os.environ.clear()
    os.environ.update({'PATH':'/usr/bin:/bin','HOME':'/nonexistent','LANG':'C.UTF-8'})


def acl_spec(principals, *, directory):
    if type(principals) is not list or len(principals)>128:raise ValueError('bounded principals required')
    ids=sorted(set(local('unix').uid(value) for value in principals))
    owner='rwx' if directory else 'rw-';client='--x' if directory else 'rw-'
    entries=['u::'+owner,'g::---','o::---']
    entries.extend('u:'+str(value)+':'+client for value in ids)
    entries.append('m::'+(client if ids else '---'))
    return ','.join(entries)


def set_acl(path,principals, *, directory):
    path=Path(path)
    if not path.is_absolute() or path.resolve(strict=True)!=path:raise ValueError('canonical ACL target required')
    info=path.lstat()
    kind=stat.S_ISDIR(info.st_mode) if directory else stat.S_ISSOCK(info.st_mode)
    if not kind or info.st_uid!=os.getuid():raise ValueError('service-owned ACL target required')
    spec=acl_spec(principals,directory=directory)
    # Exact replacement revokes stale named/default grants, not just additions.
    command=['/usr/bin/setfacl','--no-mask','--set='+spec]
    if directory:command.append('--remove-default')
    command.extend(['--',str(path)])
    subprocess.run(command,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,
                   env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'},timeout=5,check=True)
    after=path.lstat()
    if (after.st_dev,after.st_ino)!=(info.st_dev,info.st_ino):raise ValueError('ACL target changed')


def prepare_endpoint(path,grants):
    # Only nonempty private grants get filesystem connection access. The
    # dispatcher independently rechecks exact repository grants on every call.
    principals=[uid for uid,grant in grants.items() if grant['private_read']]
    set_acl(path.parent,principals,directory=True)
    set_acl(path,principals,directory=False)


def serve(store_root,socket_path,policy_path,stopping):
    transport=local('unix');store=local('store').Store(store_root)
    policy=transport.load_policy(policy_path)
    # Validate first, before ACL mutation. This remains an unprivileged process.
    access=local('access').Access(store,policy)
    with transport.Server(socket_path,store,policy,on_bound=lambda path:prepare_endpoint(path,access.grants)) as server:
        while not stopping():server.serve_once()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=('serve','initialize-empty'))
    parser.add_argument('--account',default='rras-history')
    parser.add_argument('--store',default='/var/lib/rras-engineering-history')
    parser.add_argument('--socket',default='/run/rras-engineering-history/service.sock')
    parser.add_argument('--policy',default='/etc/rras-engineering-history/access-policy.json')
    args=parser.parse_args(argv);stopped=False
    def stop(*_):
        nonlocal stopped
        stopped=True
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    try:
        service_environment()
        require_account(args.account)
        if args.operation=='initialize-empty':
            local('store').Store(args.store,create=True)
            print('{"empty_store_initialized":true,"authority_granted":false}')
        else:serve(args.store,args.socket,args.policy,lambda:stopped)
    except (ValueError,KeyError,TypeError,OSError,sqlite3.Error,subprocess.SubprocessError):
        parser.exit(1,'History service entry refused; preserve store and endpoint evidence.\n')


if __name__=='__main__':main()
