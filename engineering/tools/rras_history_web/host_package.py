"""Build/hash-check an offline synthetic dashboard host fixture. No installation."""
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import re
import stat
import subprocess

MANIFEST='release-manifest.json'
STATE=Path('/var/lib/rras-history-web-acceptance-projects-20261106')
RUNTIME=Path('/run/rras-history-web-acceptance-projects-20261106')
PYTHON=Path('/opt/rras-engineering/releases/cpython-3.13.16-ae7041461525/bin/python3.13')
SOURCE_FILES={f'engineering/tools/rras_history_web/{name}.py' for name in ('access','app','history','entry','host_package','host_driver','host_probe','stage_host')}|{
    f'engineering/tools/rras_history_web/assets/{name}' for name in ('index.html','app.css','app.js')}|{
    f'engineering/tools/rras_history/{name}.py' for name in ('contract','documents','scoped_documents','projects','store','access','unix','production_entry')}|{
    'engineering/contracts/engineering-history-v1.schema.json','engineering/contracts/engineering-history-v2.schema.json',
    'engineering/contracts/engineering-project-v1.schema.json','engineering/config/history-web/rras-engineering-history-web.service.in'}|{
    f'engineering/docs/engineering-history-phase1/templates/{name}.md' for name in ('review','checkpoint','completion')}
LIMIT=96*1024*1024


def encoded(value):return (json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode()


def decode(raw):
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('duplicate member')
            result[key]=value
        return result
    return json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite JSON')))


def regular(path,limit=32*1024*1024):
    path=Path(path)
    if not path.is_absolute() or path.resolve(strict=True)!=path:raise ValueError('canonical input required')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or not 0<=info.st_size<=limit:raise ValueError('bounded regular input required')
        raw=stream.read(limit+1)
    if len(raw)>limit:raise ValueError('input too large')
    return raw


def safe_name(name):
    if type(name) is not str:raise ValueError('path required')
    path=PurePosixPath(name)
    if (str(path)!=name or path.is_absolute() or len(name)>512 or any(p in ('..','.git','__pycache__','bin') for p in path.parts) or
            name.endswith(('.pyc','.pth')) or (name not in SOURCE_FILES and not name.startswith('vendor/'))):raise ValueError('unsafe fixture path')


def verify(candidate,expected):
    candidate=Path(candidate)
    if not candidate.is_absolute() or candidate.resolve(strict=True)!=candidate:raise ValueError('canonical candidate required')
    raw=regular(candidate/MANIFEST,512*1024)
    if type(expected) is not str or not re.fullmatch('[0-9a-f]{64}',expected) or hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('manifest changed')
    manifest=decode(raw)
    if (type(manifest) is not dict or set(manifest)!={'contract','scope','source_commit','files'} or encoded(manifest)!=raw or
            manifest['contract']!='engineering-history-web-host.v1' or manifest['scope']!='isolated-synthetic-only' or
            type(manifest['source_commit']) is not str or not re.fullmatch('[0-9a-f]{40}',manifest['source_commit']) or
            type(manifest['files']) is not dict or not SOURCE_FILES<set(manifest['files']) or len(manifest['files'])>3000):raise ValueError('invalid fixture manifest')
    files={};total=0
    for name,digest in manifest['files'].items():
        safe_name(name)
        if type(digest) is not str or not re.fullmatch('[0-9a-f]{64}',digest):raise ValueError('digest required')
        raw=regular(candidate/name);total+=len(raw)
        if total>LIMIT or hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('fixture payload changed')
        files[name]=raw
    return manifest,files


def build(source,vendor,destination,commit):
    source=Path(source).resolve(strict=True);vendor=Path(vendor).resolve(strict=True);destination=Path(destination)
    if type(commit) is not str or not re.fullmatch('[0-9a-f]{40}',commit):raise ValueError('exact source commit required')
    def git(*args):return subprocess.check_output(['/usr/bin/git','-C',str(source),*args],stderr=subprocess.PIPE,
        env={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','LANG':'C.UTF-8','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null'},timeout=30)
    if git('rev-parse','HEAD').decode().strip()!=commit:raise ValueError('source commit differs')
    files={name:git('show',commit+':'+name) for name in SOURCE_FILES}
    for path in sorted(vendor.rglob('*')):
        if path.is_dir() and not path.is_symlink():continue
        parts=path.relative_to(vendor).parts
        if any(part in ('__pycache__','bin') for part in parts) or path.suffix=='.pyc':continue
        name='vendor/'+path.relative_to(vendor).as_posix();safe_name(name);files[name]=regular(path)
    if not SOURCE_FILES<set(files) or len(files)>3000 or sum(map(len,files.values()))>LIMIT:raise ValueError('fixture bounds exceeded')
    if not destination.is_absolute() or destination.parent.resolve(strict=True)!=destination.parent:raise ValueError('canonical destination required')
    manifest={'contract':'engineering-history-web-host.v1','scope':'isolated-synthetic-only','source_commit':commit,
        'files':{name:hashlib.sha256(raw).hexdigest() for name,raw in sorted(files.items())}}
    destination.mkdir(mode=0o700)
    for name,raw in files.items():
        path=destination/name;path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        with path.open('xb') as stream:os.fchmod(stream.fileno(),0o600);stream.write(raw)
    raw=encoded(manifest)
    with (destination/MANIFEST).open('xb') as stream:os.fchmod(stream.fileno(),0o600);stream.write(raw)
    sha=hashlib.sha256(raw).hexdigest();verify(destination,sha)
    return {'candidate':str(destination),'manifest_sha256':sha,'files':len(files),'source_commit':commit,'root_mutations':False,'services_started':False}


def emit_helper(destination):
    # Root entry contains the same verifier as the unprivileged package check.
    prefix=Path(__file__).read_text().split('\ndef build(',1)[0]
    suffix=Path(__file__).with_name('stage_host.py').read_text()
    with Path(destination).open('x') as stream:stream.write(prefix+'\n'+suffix)
    return hashlib.sha256(Path(destination).read_bytes()).hexdigest()
