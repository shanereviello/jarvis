"""Passive registration of explicitly configured desktop workspaces.

Hook events register exact session files; a separate pass performs capture.
This module installs no hook, reads no ambient configuration and starts no work.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import uuid

sys.path.insert(0,str(Path(__file__).parent))
import capture_intake as intake
import capture_jobs


def configuration(path):
    path=intake.private(path)
    if path.stat().st_size>65536:raise ValueError('bounded desktop policy required')
    value=intake.local('contract').decode(path.read_bytes())
    fields={'contract','registry','spool','native_root','binary','service_socket','service_uid',
            'scope','workspaces','authorization_reference'}
    if (type(value) is not dict or set(value)!=fields or value['contract']!='engineering-desktop-capture.v1' or
            type(value['service_uid']) is not int or not 1<=value['service_uid']<2**32-1 or
            type(value['workspaces']) is not list or not 1<=len(value['workspaces'])<=32 or
            len(set(value['workspaces']))!=len(value['workspaces'])):
        raise ValueError('explicit desktop capture policy required')
    for key in ('registry','spool'):
        intake.private(value[key],True)
    native=Path(value['native_root']);info=native.lstat()
    if (not native.is_absolute() or native.resolve()!=native or not stat.S_ISDIR(info.st_mode) or
            info.st_uid!=os.getuid() or info.st_mode&0o002):
        raise ValueError('caller-owned non-world-writable native root required')
    for path in [value['binary'],value['service_socket'],*value['workspaces']]:
        if type(path) is not str or not Path(path).is_absolute() or Path(path).resolve()!=Path(path):
            raise ValueError('canonical configured paths required')
    capture_jobs.collectors.authorization(value['authorization_reference'])
    # Reuse the actual intake contract to validate the scope without inventing a work association.
    intake.local('reporting_contract').validate(dict(contract='engineering-reporting.v1',operation='source.observe',
        client_event_key='desktop-policy-validation',expected_head=None,scope=value['scope'],context=None,
        source=dict(kind='imported',namespace='capture_intake',id='desktop-validation'),occurred_at=None,
        body=dict(source=dict(namespace='codex',id='desktop-validation'),source_observed_at=None,cursor=None,
            status='unknown',gaps=[],detail='Desktop policy validation only.')))
    return value


def job_for(value,event):
    if type(event) is not dict or event.get('hook_event_name') not in ('SessionStart','UserPromptSubmit','Stop','SessionEnd'):
        raise ValueError('supported desktop lifecycle event required')
    cwd=event.get('cwd');source=event.get('transcript_path');session=event.get('session_id')
    if cwd not in value['workspaces'] or source is None:return None
    if type(session) is not str or str(uuid.UUID(session))!=session:raise ValueError('exact session identity required')
    if type(source) is not str:raise ValueError('exact transcript path required')
    p=Path(source);root=Path(value['native_root'])
    if not p.is_absolute() or p.resolve()!=p or not p.is_relative_to(root) or p==root:
        raise ValueError('selected transcript outside configured native root')
    # Each exact path is its own immutable segment, including rotated files.
    segment=hashlib.sha256(source.encode()).hexdigest()[:32]
    key=hashlib.sha256((session+'\0'+source).encode()).hexdigest()
    return dict(contract='engineering-capture-jobs.v2',spool=value['spool'],service_socket=value['service_socket'],
        service_uid=value['service_uid'],jobs=[dict(id='desktop-'+key[:32],source=source,session=session,
            binary=value['binary'],scope=value['scope'],context=None,authorization_reference=value['authorization_reference'],
            source_segment=segment)])


def register(value,event):
    job=job_for(value,event)
    if job is None:return dict(registered=False,reason='workspace_or_transcript_not_selected')
    registry=Path(value['registry']);key=job['jobs'][0]['id'].removeprefix('desktop-')
    destination=registry/(key+'.json');raw=intake.local('contract').encoded(dict(workspace=event['cwd'],job=job))
    lock=registry/'.registry.lock';fd=os.open(lock,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        intake.private(lock);fcntl.flock(fd,fcntl.LOCK_EX)
        if destination.exists() or destination.is_symlink():
            intake.private(destination)
            if destination.read_bytes()!=raw:raise ValueError('registered desktop source changed')
            return dict(registered=False,reason='already_registered')
        names=[x.name for x in registry.iterdir() if re.fullmatch('[0-9a-f]{32}\\.json',x.name)]
        if len(names)>=4096:raise ValueError('desktop registry capacity reached')
        temporary=registry/(key+'.pending')
        if temporary.exists() or temporary.is_symlink():
            intake.private(temporary)
            if temporary.read_bytes()!=raw:raise ValueError('interrupted desktop registration differs')
            os.replace(temporary,destination);intake.sync(registry)
            return dict(registered=True,reason='recovered_interrupted_registration')
        out=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        try:
            with os.fdopen(out,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
            os.replace(temporary,destination);intake.sync(registry)
        finally:
            if temporary.exists():temporary.unlink()
        return dict(registered=True,reason='selected_exact_source')
    finally:os.close(fd)


def run_once(value,*,send=None,limit=32):
    if type(limit) is not int or not 1<=limit<=32:raise ValueError('bounded desktop pass required')
    registry=Path(value['registry']);lock=registry/'.registry.lock';fd=os.open(lock,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        intake.private(lock);fcntl.flock(fd,fcntl.LOCK_EX)
        names=sorted(x.name for x in registry.iterdir() if re.fullmatch('[0-9a-f]{32}\\.json',x.name))
        if len(names)>4096:raise ValueError('desktop registry capacity reached')
        cursor=registry/'.cursor';after=''
        if cursor.exists() or cursor.is_symlink():
            intake.private(cursor);after=cursor.read_text()
            if not re.fullmatch('[0-9a-f]{32}\\.json',after):raise ValueError('invalid desktop cursor')
        ordered=[n for n in names if n>after]+[n for n in names if n<=after];selected=[];revoked=0
        considered=ordered[:limit]
        for name in considered:
            path=intake.private(registry/name)
            if path.stat().st_size>1024*1024:raise ValueError('bounded desktop registry entry required')
            envelope=intake.local('contract').decode(path.read_bytes())
            if type(envelope) is not dict or set(envelope)!={'workspace','job'}:raise ValueError('exact desktop registry entry required')
            if envelope['workspace'] not in value['workspaces']:
                revoked+=1;continue
            item=capture_jobs.validate_configuration(envelope['job']);job=item['jobs'][0]
            reconstructed=job_for(value,dict(hook_event_name='SessionStart',cwd=envelope['workspace'],
                transcript_path=job['source'],session_id=job['session']))
            if item!=reconstructed or name!=job['id'].removeprefix('desktop-')+'.json':
                raise ValueError('desktop registry policy changed')
            selected.append(item)
        if considered:
            # Replace atomically. A stale temporary cursor cannot prevent future passes.
            temporary=registry/'.cursor.next'
            if temporary.exists() or temporary.is_symlink():
                intake.private(temporary);temporary.unlink()
            out=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            with os.fdopen(out,'w') as stream:stream.write(considered[-1]);stream.flush();os.fsync(stream.fileno())
            os.replace(temporary,cursor);intake.sync(registry)
    finally:os.close(fd)
    results=[capture_jobs.run_once(item,send=send) for item in selected]
    return dict(contract='engineering-desktop-capture-pass.v1',sources=len(selected),revoked_sources=revoked,passes=results,models_started=0)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('operation',choices=('register','run-once'))
    parser.add_argument('--config',required=True);parser.add_argument('--limit',type=int,default=32);args=parser.parse_args()
    try:
        value=configuration(args.config)
        if args.operation=='register':
            raw=sys.stdin.buffer.read(65537)
            if len(raw)>65536:raise ValueError('bounded hook event required')
            result=register(value,intake.local('contract').decode(raw))
            # Stop hooks require JSON; an empty object grants no authority and
            # never includes prompt, transcript or registration details.
            print('{}')
        else:result=run_once(value,limit=args.limit);print(json.dumps(result,allow_nan=False))
    except (ValueError,OSError,TypeError,KeyError):
        parser.exit(1,'Desktop capture registration or pass refused; retained sources and queue unchanged.\n')


if __name__=='__main__':main()
