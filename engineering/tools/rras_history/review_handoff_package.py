"""Pinned synthetic historical-review document handoff fixture package."""
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import re
import stat
import subprocess

STATE=Path('/var/lib/rras-history-review-handoff-acceptance-20261027')
SERVICE=61111
UNKNOWN=61113
LIMIT=12*1024*1024
MANIFEST='release-manifest.json'
NATIVE=('activity', 'approval', 'approved_launch', 'credentials', 'document_approval', 'draft_pr_connector', 'managed_events', 'manual_runner', 'native_observation', 'native_task_cli', 'operator_control', 'post_validation', 'publication', 'publication_capture', 'publication_custody', 'publication_handoff', 'publication_policy', 'publication_transport', 'publish_workflow_views', 'repository_admission', 'review_gate', 'task_contract', 'validation_execution', 'validation_workspace', 'wait_worker', 'workflow_finish', 'workflow_journal', 'workflow_publication', 'workflow_read_stdio', 'workflow_read_tools', 'workflow_records', 'probe_workflow_host', 'probe_approved_launch', 'document_host_cases', 'engineering_export')
HISTORY=('access','contract','documents','store','unix','interactive','production_entry','managed_link','link_delivery','managed_sync',
         'managed_host_package','managed_host_probe','managed_host_driver','managed_review','review_document_link','review_document_export',
         'review_handoff_package','review_handoff_probe','review_handoff_driver')
SOURCE_FILES=set('engineering/tools/rras_native/'+name+'.py' for name in NATIVE)|set(
    'engineering/tools/rras_history/'+name+'.py' for name in HISTORY)|set('engineering/contracts/'+name for name in (
    'engineering-history-v1.schema.json','engineering-managed-export-v1.schema.json','workflow-v1.schema.json','examples/library-managed.json'))|set(
    'engineering/docs/engineering-history-phase1/templates/'+name+'.md' for name in ('review','checkpoint','completion'))
GENERATED={'engineering/tools/rras_native/library-managed.json','engineering/tools/rras_native/profile.json','engineering/tools/rras_native/codex-config.toml'}


def encoded(value):return (json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode()


def decode(raw):
    def unique(pairs):
        value={}
        for key,item in pairs:
            if key in value:raise ValueError('duplicate fixture JSON member')
            value[key]=item
        return value
    return json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('invalid JSON number')))


def regular(path,limit=4*1024*1024):
    path=Path(path)
    if not path.is_absolute() or path.resolve(strict=True)!=path:raise ValueError('canonical fixture input required')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_size>limit:raise ValueError('bounded regular fixture input required')
        with os.fdopen(os.dup(fd),'rb') as stream:raw=stream.read(limit+1)
        if len(raw)>limit:raise ValueError('fixture input exceeds bound')
        return raw
    finally:os.close(fd)


def safe_name(name):
    if type(name) is not str:raise ValueError('fixture path required')
    p=PurePosixPath(name)
    if (p.is_absolute() or str(p)!=name or any(part in ('..','.git','__pycache__') for part in p.parts) or
            name.endswith(('.pth','.pyc')) or (name not in (SOURCE_FILES|GENERATED) and not name.startswith('vendor/'))):
        raise ValueError('unsafe fixture payload path')


def verify(candidate,expected):
    candidate=Path(candidate)
    if not candidate.is_absolute() or candidate.resolve(strict=True)!=candidate:raise ValueError('canonical candidate required')
    raw=regular(candidate/MANIFEST,256*1024)
    if type(expected) is not str or not re.fullmatch('[0-9a-f]{64}',expected) or hashlib.sha256(raw).hexdigest()!=expected:
        raise ValueError('fixture manifest changed')
    manifest=decode(raw)
    if (set(manifest)!={'contract','scope','source_commit','files'} or encoded(manifest)!=raw or
            manifest['contract']!='engineering-review-handoff-host.v1' or manifest['scope']!='isolated-synthetic-only' or
            not re.fullmatch('[0-9a-f]{40}',manifest['source_commit']) or type(manifest['files']) is not dict or
            not (SOURCE_FILES|GENERATED)<set(manifest['files']) or len(manifest['files'])>300):raise ValueError('fixture manifest invalid')
    files={};size=0
    for name,sha in manifest['files'].items():
        safe_name(name);raw=regular(candidate/name)
        if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('fixture payload changed')
        files[name]=raw;size+=len(raw)
        if size>LIMIT:raise ValueError('fixture exceeds bound')
    if (files['engineering/tools/rras_native/profile.json']!=b'{}\n' or
            files['engineering/tools/rras_native/codex-config.toml']!=b'sandbox_mode="read-only"\n'):
        raise ValueError('synthetic session bytes required')
    return manifest,files


def build(source,vendor,destination,commit):
    source=Path(source).resolve(strict=True);vendor=Path(vendor).resolve(strict=True);destination=Path(destination)
    if not re.fullmatch('[0-9a-f]{40}',commit):raise ValueError('exact committed source required')
    def git(*args):return subprocess.check_output(['/usr/bin/git','-C',str(source),*args],stderr=subprocess.PIPE,
        env={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','LANG':'C.UTF-8','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null'},timeout=30)
    if git('rev-parse','HEAD').decode().strip()!=commit:raise ValueError('exact current commit required')
    files={name:git('show',commit+':'+name) for name in SOURCE_FILES}
    files['engineering/tools/rras_native/library-managed.json']=files['engineering/contracts/examples/library-managed.json']
    files['engineering/tools/rras_native/profile.json']=b'{}\n'
    files['engineering/tools/rras_native/codex-config.toml']=b'sandbox_mode="read-only"\n'
    for path in sorted(vendor.rglob('*')):
        if path.is_dir() and not path.is_symlink():continue
        if '__pycache__' in path.parts or path.suffix=='.pyc':continue
        name='vendor/'+path.relative_to(vendor).as_posix();safe_name(name);files[name]=regular(path)
    manifest={'contract':'engineering-review-handoff-host.v1','scope':'isolated-synthetic-only','source_commit':commit,
        'files':{name:hashlib.sha256(raw).hexdigest() for name,raw in sorted(files.items())}}
    destination.mkdir(mode=0o700)
    for name,raw in files.items():
        path=destination/name;path.parent.mkdir(mode=0o700,parents=True,exist_ok=True);path.write_bytes(raw)
    raw=encoded(manifest);(destination/MANIFEST).write_bytes(raw);sha=hashlib.sha256(raw).hexdigest()
    verify(destination,sha)
    return {'phase':'offline_review_handoff_candidate_verified','manifest_sha256':sha,'source_commit':commit,
            'files':len(files),'root_mutations':False,'api_calls':0}


def emit_helper(destination):
    prefix=Path(__file__).read_text().split('\ndef build(',1)[0]
    suffix=Path(__file__).with_name('stage_review_handoff.py').read_text()
    with Path(destination).open('x') as f:f.write(prefix+'\n'+suffix)
    return hashlib.sha256(Path(destination).read_bytes()).hexdigest()
