"""Pinned isolated document approval fixture, with an exact synthetic runner."""
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path,PurePosixPath
import re
import stat

STATE=Path('/var/lib/rras-document-approval-acceptance-20261025')
DIAGNOSTICS=Path('/var/lib/rras-document-approval-acceptance-diagnostics-20261025')
MANIFEST='document-host-manifest.json'
CONTRACT='engineering-document-host.v1'
LIMIT=12*1024*1024


def local(name):
    spec=importlib.util.spec_from_file_location('document_package_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def encoded(value):return (json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)+'\n').encode()


def decode(raw):
    def unique(pairs):
        value={}
        for key,item in pairs:
            if key in value:raise ValueError('duplicate fixture manifest key')
            value[key]=item
        return value
    return json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('invalid number')))


def regular(path,limit=4*1024*1024):
    path=Path(path)
    if not path.is_absolute() or path.resolve(strict=True)!=path:raise ValueError('canonical fixture input required')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_size>limit:
            raise ValueError('bounded single-link regular fixture input required')
        with os.fdopen(os.dup(fd),'rb') as stream:raw=stream.read(limit+1)
        if len(raw)>limit:raise ValueError('fixture input exceeded bound')
        return raw
    finally:os.close(fd)


def safe_name(name):
    if type(name) is not str:raise ValueError('fixture name required')
    p=PurePosixPath(name)
    if (p.is_absolute() or str(p)!=name or any(part in ('..','.git','__pycache__') for part in p.parts) or
            name.endswith(('.pth','.pyc')) or not name.startswith(('engineering/','vendor/'))):
        raise ValueError('unsafe fixture name')


def fake_worker(files):
    name='engineering/tools/rras_native/probe_approved_launch.py';tree=ast.parse(files[name])
    values=[node.value for node in tree.body if isinstance(node,ast.Assign) and
            any(isinstance(target,ast.Name) and target.id=='FAKE_WORKER' for target in node.targets)]
    if len(values)!=1:raise ValueError('exact fake worker constant required')
    worker=ast.literal_eval(values[0])
    if type(worker) is not str:raise ValueError('literal fake worker required')
    return worker.encode()


def verify(candidate,expected):
    candidate=Path(candidate)
    if not candidate.is_absolute() or candidate.resolve(strict=True)!=candidate:raise ValueError('canonical fixture candidate required')
    raw=regular(candidate/MANIFEST,256*1024)
    if type(expected) is not str or not re.fullmatch('[0-9a-f]{64}',expected) or hashlib.sha256(raw).hexdigest()!=expected:
        raise ValueError('fixture manifest changed')
    manifest=decode(raw)
    if (set(manifest)!={'contract','scope','source_commit','files','synthetic_runner_sha256'} or encoded(manifest)!=raw or
            manifest['contract']!=CONTRACT or manifest['scope']!='isolated-synthetic-only' or
            not re.fullmatch('[0-9a-f]{40}',manifest['source_commit']) or type(manifest['files']) is not dict or
            not 20<=len(manifest['files'])<=300):raise ValueError('invalid fixture manifest')
    files={};size=0
    for name,sha in manifest['files'].items():
        safe_name(name);raw=regular(candidate/name)
        if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('fixture payload changed')
        files[name]=raw;size+=len(raw)
        if size>LIMIT:raise ValueError('fixture payload exceeds bound')
    worker=fake_worker(files)
    if (files['engineering/tools/rras_native/manual_runner.py']!=worker or
            hashlib.sha256(worker).hexdigest()!=manifest['synthetic_runner_sha256']):raise ValueError('exact fake runner required')
    for name in ('document_approval','document_host_cases','probe_document_approval','probe_workflow_host'):
        if 'engineering/tools/rras_native/'+name+'.py' not in files:raise ValueError('missing document fixture module')
    return manifest,files


def build(source,vendor,destination,commit):
    a=local('activity');source=a.canonical_repo(source);vendor=Path(vendor).resolve(strict=True);destination=Path(destination)
    if not re.fullmatch('[0-9a-f]{40}',commit) or a.git(source,'rev-parse','HEAD').decode().strip()!=commit:
        raise ValueError('exact current committed source required')
    package=local('prepare_workflow_release');prefix='engineering/tools/rras_native/'
    names=[prefix+name for name in (*package.MODULES,*package.ASSETS)]+list(package.DOCUMENT_FILES)
    names += [prefix+name+'.py' for name in ('probe_approved_launch','probe_workflow_host','document_host_cases','probe_document_approval')]
    names += ['engineering/contracts/workflow-v1.schema.json']
    files={name:a.git(source,'show',commit+':'+name) for name in names}
    files[prefix+'library-managed.json']=a.git(source,'show',commit+':engineering/contracts/examples/library-managed.json')
    files[prefix+'profile.json']=b'{}\n'
    files[prefix+'codex-config.toml']=b'sandbox_mode="read-only"\n'
    worker=fake_worker(files);files[prefix+'manual_runner.py']=worker
    package.verify_module_closure(files)
    for path in sorted(vendor.rglob('*')):
        if path.is_dir() and not path.is_symlink():continue
        if '__pycache__' in path.parts or path.suffix=='.pyc':continue
        name='vendor/'+path.relative_to(vendor).as_posix();safe_name(name);files[name]=regular(path)
    manifest={'contract':CONTRACT,'scope':'isolated-synthetic-only','source_commit':commit,
              'synthetic_runner_sha256':hashlib.sha256(worker).hexdigest(),
              'files':{name:hashlib.sha256(raw).hexdigest() for name,raw in sorted(files.items())}}
    destination.mkdir(mode=0o700)
    for name,raw in files.items():
        path=destination/name;path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        with path.open('xb') as stream:stream.write(raw)
    raw=encoded(manifest);(destination/MANIFEST).write_bytes(raw);sha=hashlib.sha256(raw).hexdigest()
    verify(destination,sha)
    return {'phase':'offline_document_host_candidate_verified','manifest_sha256':sha,'source_commit':commit,
            'files':len(files),'root_mutations':False,'services_started':False,'api_calls':0}


def emit_helper(destination):
    prefix=Path(__file__).read_text().split('\ndef build(',1)[0]
    # The stdlib bootstrap never imports candidate code; staging precedes execution.
    suffix=Path(__file__).with_name('stage_document_host.py').read_text()
    with Path(destination).open('x') as stream:stream.write(prefix+'\n'+suffix)
    return hashlib.sha256(Path(destination).read_bytes()).hexdigest()
