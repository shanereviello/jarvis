"""Root-only protected-custody loader and review commit preparation; no network."""
import importlib.util
import json
import os
from pathlib import Path
import stat


def local(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def root_bytes(path,limit):
    p=Path(path);local('approved_launch').trusted(p)
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        st=os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_uid!=0 or st.st_mode&0o022 or st.st_size>limit:raise ValueError('protected bounded custody file required')
        with os.fdopen(os.dup(fd),'rb') as f:data=f.read(limit+1)
        if len(data)>limit:raise ValueError('custody file too large')
        return data
    finally:os.close(fd)


def load(custody):
    if os.geteuid()!=0:raise ValueError('administrator custody verification required')
    a=local('activity');custody=Path(custody)
    receipt=json.loads(root_bytes(custody/'capture.json',1024*1024))
    data={}
    for name,expected in receipt['files'].items():
        p=Path(name)
        if p.is_absolute() or '..' in p.parts or str(p)!=name or len(p.parts)>2:raise ValueError('invalid custody member')
        content=root_bytes(custody/p,4*1024*1024)
        if a.digest(content)!=expected:raise ValueError('custody content changed')
        data[name]=content
    objects={name:json.loads(data[name+'.json']) for name in ('review','host-result','evidence','manifest')}
    result=objects['host-result']
    if objects['review'].get('review_branch')!=result.get('review_branch'):raise ValueError('review branch binding changed')
    if receipt['authorization_id']!=result['authorization_id'] or receipt['assigned_branch']!=result.get('review_branch','codex/task-'+result['run_id']) or receipt['export_id']!=objects['evidence']['export']['export_id']:
        raise ValueError('custody identity mismatch')
    files={name.removeprefix('artifacts/'):content for name,content in data.items() if name.startswith('artifacts/')}
    return dict(assigned_branch=receipt['assigned_branch'],review=objects['review'],host_result=result,
                evidence=objects['evidence'],manifest=objects['manifest'],files=files)


def prepare(custody,policy,destination):
    a=local('activity');inputs=load(custody)
    local('approved_launch').trusted(Path(destination).parent)
    policy_bytes=root_bytes(policy,1024*1024);policy=json.loads(policy_bytes)
    result=local('publication').prepare(inputs['review']['canonical_repository'],destination,policy=policy,**inputs)
    result['policy_sha256']=a.digest(policy_bytes)
    # Separate from the checkout so it cannot accidentally be committed/uploaded.
    a.absent(Path(str(destination)+'.prepared.json'),a.encoded(result))
    return result
