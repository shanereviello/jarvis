"""Root-reviewed Git bundle to operator SSH publication; no worker credentials.

CLI is operator-only, not an MCP tool. Root exports source history + a narrow
manifest; the named operator imports/pushes using their existing SSH identity.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import pwd
import subprocess

LIMIT=64*1024*1024


def local(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def git(argv):
    return subprocess.run(['/usr/bin/git','-c','core.hooksPath=/dev/null','-c','core.fsmonitor=false',*argv],
        env={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','LANG':'C.UTF-8','GIT_CONFIG_NOSYSTEM':'1',
             'GIT_CONFIG_GLOBAL':'/dev/null','GIT_TERMINAL_PROMPT':'0'},
        stdin=subprocess.DEVNULL,capture_output=True,check=True,timeout=60).stdout


def export(prepared_path,policy_path,destination,operator='shanereviello'):
    if os.geteuid()!=0:raise ValueError('administrator export required')
    a=local('activity');custody=local('publication_custody');transport=local('publication_transport')
    policy_bytes=custody.root_bytes(policy_path,1024*1024);policy=json.loads(policy_bytes)
    prepared=json.loads(custody.root_bytes(prepared_path,1024*1024))
    if prepared['policy_sha256']!=a.digest(policy_bytes):raise ValueError('publication policy changed')
    transport.verify(prepared,policy)
    uid=pwd.getpwnam(operator).pw_uid
    if uid in (0,996,997):raise ValueError('separate operator identity required')
    destination=Path(destination);local('approved_launch').trusted(destination.parent)
    if destination.exists() or destination.is_symlink():raise ValueError('fresh handoff destination required')
    destination.mkdir(mode=0o700)
    bundle=destination/'review.bundle'
    git(['-C',prepared['checkout'],'bundle','create',str(bundle),'refs/heads/'+prepared['branch']])
    if bundle.stat().st_size>LIMIT:raise ValueError('review bundle too large; retain partial handoff')
    data=bundle.read_bytes()
    # No private custody paths, requests, logs or credentials in this manifest.
    keys=('repository_id','remote','branch','refspec','commit','baseline','export_id','action','force',
          'human_publication_confirmation_required','merge_authorized','deploy_authorized',
          'pr_base_branch','task_id','native_task','native_run','validation_exit','worker_stop_verified','host_stop_verified')
    record={'schema_version':1,'operator_uid':uid,'prepared':{k:prepared[k] for k in keys},
            'policy':policy,'bundle_sha256':a.digest(data),'bundle_size':len(data)}
    a.absent(destination/'handoff.json',a.encoded(record))
    bundle.chmod(0o444);(destination/'handoff.json').chmod(0o444)
    destination.chmod(0o555)  # Explicit despite root's umask; source is intended for review/publication.
    return record


def read(package):
    a=local('activity');custody=local('publication_custody');package=Path(package)
    record=json.loads(custody.root_bytes(package/'handoff.json',1024*1024))
    if record['schema_version']!=1 or os.getuid()!=record['operator_uid'] or os.getuid() in (0,996,997):
        raise ValueError('named human operator required')
    data=custody.root_bytes(package/'review.bundle',LIMIT)
    if len(data)!=record['bundle_size'] or a.digest(data)!=record['bundle_sha256']:raise ValueError('handoff bundle changed')
    return record,data


def import_review(package,destination):
    a=local('activity');record,data=read(package);destination=Path(destination)
    if destination.exists() or destination.is_symlink():raise ValueError('fresh operator workspace required')
    destination.mkdir(mode=0o700);destination.chmod(0o700)
    bundle=destination/'review.bundle';a.absent(bundle,data)
    checkout=destination/'repo'
    git(['clone','--quiet','--branch',record['prepared']['branch'],str(bundle),str(checkout)])
    git(['-C',str(checkout),'remote','remove','origin'])
    prepared=dict(record['prepared'],checkout=str(checkout))
    local('publication_transport').verify(prepared,record['policy'])
    return prepared


def publish(package,workspace):
    record,_=read(package);workspace=Path(workspace)
    st=workspace.lstat()
    if workspace.is_symlink() or st.st_uid!=os.getuid() or st.st_mode&0o077:raise ValueError('private operator workspace required')
    prepared=dict(record['prepared'],checkout=str(workspace/'repo'))
    return local('publication_transport').publish(prepared,record['policy'],workspace/'publication-receipt.json')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--action',choices=('export','import','publish','review'),required=True)
    for name in ('prepared','policy','package','workspace'):p.add_argument('--'+name)
    args=p.parse_args()
    if args.action=='export':answer=export(args.prepared,args.policy,args.package)
    elif args.action=='import':answer=import_review(args.package,args.workspace)
    elif args.action=='review':
        record,_=read(args.package)
        print(local('review_gate').render(record));raise SystemExit(0)
    else:answer=publish(args.package,args.workspace)
    print(json.dumps(answer));raise SystemExit(0 if answer.get('status','published')=='published' else 1)
