"""Bounded pinned synthetic managed-link host fixture; no production install."""
import hashlib
import json
from pathlib import Path,PurePosixPath
import re
import stat

STATE=Path('/var/lib/rras-history-managed-link-acceptance-20261024')
SERVICE=61101
CLIENT=61102
UNKNOWN=61103
LIMIT=8*1024*1024
HISTORY=('access','contract','documents','store','unix','interactive','production_entry','managed_link','link_delivery',
         'managed_host_package','managed_host_driver','managed_host_probe')
NATIVE=('workflow_records','workflow_journal','engineering_export')
SOURCE_FILES=set('engineering/tools/rras_history/'+name+'.py' for name in HISTORY)|set(
    'engineering/tools/rras_native/'+name+'.py' for name in NATIVE)|set('engineering/contracts/'+name for name in (
    'engineering-history-v1.schema.json','engineering-managed-export-v1.schema.json','workflow-v1.schema.json','examples/library-managed.json'))|set(
    'engineering/docs/engineering-history-phase1/templates/'+name+'.md' for name in ('review','checkpoint','completion'))


def encoded(value):return (json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode()


def decode(raw):
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('duplicate fixture manifest member')
            result[key]=value
        return result
    return json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('invalid JSON number')))


def regular(path,limit=4*1024*1024):
    info=path.lstat()
    if path.resolve(strict=True)!=path or not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_size>limit:
        raise ValueError('bounded canonical regular fixture payload required')
    raw=path.read_bytes()
    if len(raw)>limit:raise ValueError('fixture payload grew beyond bound')
    return raw


def safe_name(name):
    if type(name) is not str:raise ValueError('fixture name required')
    p=PurePosixPath(name)
    if p.is_absolute() or str(p)!=name or any(part in ('..','.git','__pycache__') for part in p.parts) or name.endswith(('.pth','.pyc')):
        raise ValueError('unsafe fixture payload path')
    if name not in SOURCE_FILES and not name.startswith('vendor/'):raise ValueError('unlisted fixture payload')


def verify(candidate,expected):
    candidate=Path(candidate)
    if not candidate.is_absolute() or candidate.resolve(strict=True)!=candidate:raise ValueError('canonical fixture candidate required')
    raw=regular(candidate/'managed-host-manifest.json',256*1024)
    if type(expected) is not str or not re.fullmatch('[0-9a-f]{64}',expected) or hashlib.sha256(raw).hexdigest()!=expected:
        raise ValueError('fixture manifest differs')
    manifest=decode(raw)
    if (set(manifest)!={'contract','scope','source_commit','files'} or encoded(manifest)!=raw or
            manifest['contract']!='engineering-managed-host.v1' or manifest['scope']!='isolated-synthetic-only' or
            not re.fullmatch('[0-9a-f]{40}',manifest['source_commit']) or type(manifest['files']) is not dict or
            not SOURCE_FILES<set(manifest['files']) or len(manifest['files'])>256):raise ValueError('fixture manifest invalid')
    files={}
    for name,sha in manifest['files'].items():
        safe_name(name);raw=regular(candidate/name)
        if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('fixture payload differs')
        files[name]=raw
        if sum(map(len,files.values()))>LIMIT:raise ValueError('fixture payload exceeds bound')
    return manifest,files


def build(source,vendor,destination,commit):
    source=Path(source).resolve(strict=True);vendor=Path(vendor).resolve(strict=True);destination=Path(destination)
    if not re.fullmatch('[0-9a-f]{40}',commit):raise ValueError('exact source commit required')
    files={name:regular(source/name) for name in SOURCE_FILES}
    for path in sorted(vendor.rglob('*')):
        if path.is_dir() and not path.is_symlink():continue
        if '__pycache__' in path.parts or path.suffix=='.pyc':continue
        name='vendor/'+path.relative_to(vendor).as_posix();safe_name(name);files[name]=regular(path)
    manifest={'contract':'engineering-managed-host.v1','scope':'isolated-synthetic-only','source_commit':commit,
              'files':{name:hashlib.sha256(raw).hexdigest() for name,raw in sorted(files.items())}}
    destination.mkdir(mode=0o700)
    for name,raw in files.items():
        path=destination/name;path.parent.mkdir(mode=0o700,parents=True,exist_ok=True);path.write_bytes(raw)
    raw=encoded(manifest);(destination/'managed-host-manifest.json').write_bytes(raw);sha=hashlib.sha256(raw).hexdigest()
    verify(destination,sha)
    return {'manifest_sha256':sha,'files':len(files),'source_commit':commit,'root_mutations':False,'api_calls':0}


def emit_helper(destination):
    prefix=Path(__file__).read_text().split('\ndef build(',1)[0]
    bootstrap=Path(__file__).with_name('stage_managed_host.py').read_text()
    with Path(destination).open('x') as stream:stream.write(prefix+'\n'+bootstrap)
    return hashlib.sha256(Path(destination).read_bytes()).hexdigest()
