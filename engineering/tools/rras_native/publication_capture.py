"""Operator-only stopped-worker evidence capture; no push, keys, or model calls."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import stat


def local(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def worker_bytes(path,limit):
    path=Path(path)
    if not path.is_absolute():raise ValueError('absolute worker evidence required')
    # After global UID stop, ancestors must exclude every other untrusted writer.
    for parent in path.parents:
        st=parent.lstat()
        if not stat.S_ISDIR(st.st_mode) or st.st_uid not in (0,996) or st.st_mode&0o022:
            raise ValueError('unprotected worker evidence ancestor')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        st=os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_uid!=996 or st.st_mode&0o022 or st.st_size>limit:
            raise ValueError('invalid worker evidence file')
        data=b''
        while len(data)<=limit:
            part=os.read(fd,min(65536,limit+1-len(data)))
            if not part:break
            data+=part
        if len(data)>limit:raise ValueError('worker evidence too large')
        return data
    finally:os.close(fd)


def capture(state,authorization_id,destination):
    if os.geteuid()!=0:raise ValueError('administrator capture required')
    if not re.fullmatch('[0-9a-f]{32}',authorization_id):raise ValueError('exact authorization required')
    a=local('activity');launch=local('approved_launch');approval=local('approval')
    state=launch.trusted(state);destination=Path(destination)
    launch.trusted(destination.parent)
    if destination.exists() or destination.is_symlink():raise ValueError('fresh custody destination required')
    result_path=launch.trusted(state/(authorization_id+'.result.json'))
    result=a.load(result_path)
    link=a.load(launch.trusted(state/(authorization_id+'.launch.json')))
    if result!={**link,'service_exit':0,'host_stop_verified':True} or link['authorization_id']!=authorization_id:
        raise ValueError('successful stopped launch result required')
    review=approval.read_review(state,link['review_id'])
    if review['submission_id']!=link['submission_id']:raise ValueError('submission mismatch')
    launch.slot()  # Require current unit absence and no UID996 processes, not just an old receipt.
    work=Path(link['work'])
    evidence_bytes=worker_bytes(work/'evidence.json',1024*1024)
    evidence=json.loads(evidence_bytes)
    export_id=evidence['export']['export_id']
    if not re.fullmatch('[0-9a-f]{64}',export_id):raise ValueError('exact export digest required')
    export=work/'index'/review['request']['task_id']/'exports'/export_id
    if evidence['export']['path']!=str(export):raise ValueError('unexpected export path')
    manifest_bytes=worker_bytes(export/'manifest.json',1024*1024);manifest=json.loads(manifest_bytes)
    if a.digest(a.encoded(manifest))!=export_id:raise ValueError('manifest mismatch')
    if not 1<=len(manifest['files'])<=10:raise ValueError('bounded artifact set required')
    files={}
    for name,info in manifest['files'].items():
        if not re.fullmatch(r'(changes\.patch|status\.porcelain|index\.patch|reported-log-[0-9]\.txt|additional-artifact-[01]\.json)',name):
            raise ValueError('unexpected artifact name')
        data=worker_bytes(export/name,4*1024*1024)
        if len(data)!=info['size_bytes'] or a.digest(data)!=info['sha256']:raise ValueError('artifact changed')
        files[name]=data
    launch.slot()  # Detect a launch that appeared during capture; never release/clear its slot.
    destination.mkdir(mode=0o700)
    for name,obj in [('review.json',review),('host-result.json',result),('evidence.json',evidence),('manifest.json',manifest)]:
        a.absent(destination/name,a.encoded(obj))
    artifacts=destination/'artifacts';artifacts.mkdir(mode=0o700)
    for name,data in files.items():a.absent(artifacts/name,data)
    receipt={'schema_version':1,'authorization_id':authorization_id,'export_id':export_id,
             'assigned_branch':'codex/task-'+link['run_id'],'worker_state_mutated':False,
             'files':{str(p.relative_to(destination)):a.digest(p.read_bytes()) for p in destination.rglob('*') if p.is_file()}}
    a.absent(destination/'capture.json',a.encoded(receipt))
    return receipt

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('state','authorization-id','destination'):p.add_argument('--'+name,required=True)
    args=p.parse_args();answer=capture(args.state,args.authorization_id,args.destination)
    print(json.dumps({'captured':True,'export_id':answer['export_id'],'assigned_branch':answer['assigned_branch']}))
