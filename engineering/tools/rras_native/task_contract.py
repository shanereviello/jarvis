"""Shared bounded request validation; no executor or credential dependency."""
import importlib.util
from pathlib import Path

def _activity():
    spec=importlib.util.spec_from_file_location("activity",Path(__file__).with_name("activity.py"))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def validate_request(r):
    a=_activity()
    fields={'schema_version','task_id','repository_id','objective','allowed_paths','validation_argv',
            'worker_timeout_seconds','validation_timeout_seconds','commit_policy'}
    if set(r)!=fields or r['schema_version']!=1:raise ValueError('invalid task request')
    a.identifier(r['task_id']);a.identifier(r['repository_id'])
    if not isinstance(r['objective'],str) or not r['objective'].strip() or len(r['objective'].encode())>16384:
        raise ValueError('bounded objective required')
    paths=r['allowed_paths']
    if not isinstance(paths,list) or not 0<len(paths)<=128 or len(set(paths))!=len(paths):raise ValueError('exact allowed paths required')
    for name in paths:
        if not isinstance(name,str) or not name or '\x00' in name:raise ValueError('invalid allowed path')
        p=Path(name)
        if p.is_absolute() or str(p)!=name or any(x in ('.','..','.git') for x in p.parts) or name in ('AGENTS.md','RRAS_TASK.md'):
            raise ValueError('unsafe or reserved allowed path')
    argv=r['validation_argv']
    if not isinstance(argv,list) or not 0<len(argv)<=64 or any(not isinstance(x,str) or not x or '\x00' in x or len(x)>4096 for x in argv) or not Path(argv[0]).is_absolute():
        raise ValueError('reviewed absolute validation argv required')
    for key,maximum in [('worker_timeout_seconds',300),('validation_timeout_seconds',60)]:
        if type(r[key]) is not int or not 0<r[key]<=maximum:raise ValueError('invalid timeout')
    if r['commit_policy']!='leave_uncommitted':raise ValueError('only review-first edits admitted')
    return r
