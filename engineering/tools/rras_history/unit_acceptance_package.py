"""Pinned actual-unit fixture payload; no staging or systemd mutations here."""
import hashlib
import importlib.util
import json
from pathlib import Path,PurePosixPath
import re
import stat

CORE=('access','contract','documents','store','unix','interactive','interactive_cli','production_entry','client_entry',
      'production_package','history_acceptance_package','host_acceptance','unit_acceptance','unit_acceptance_probe')
# Explicitly freeze names in the bootstrap; importing runtime code is unnecessary.
SOURCE_FILES=set('engineering/tools/rras_history/'+name+'.py' for name in CORE)|{
    'engineering/contracts/engineering-history-v1.schema.json','runtime-manifest.json'}|set(
    'engineering/docs/engineering-history-phase1/templates/'+name+'.md' for name in ('review','checkpoint','completion'))|set(
    'deployment/'+name for name in ('rras-engineering-history.service','access-policy.json','install-plan.json','rras-history-client','ROLLBACK.md'))
LIMIT=8*1024*1024


def encoded(value):return (json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode()


def decode(raw):
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('duplicate unit manifest key')
            result[key]=value
        return result
    return json.loads(raw,object_pairs_hook=unique)


def regular(path,maximum=4*1024*1024):
    info=path.lstat()
    if path.resolve(strict=True)!=path or not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_size>maximum:
        raise ValueError('bounded regular fixture payload required')
    raw=path.read_bytes()
    if len(raw)>maximum:raise ValueError('fixture grew beyond bound')
    return raw


def safe_name(name):
    if type(name) is not str:raise ValueError('unit payload name required')
    path=PurePosixPath(name)
    if path.is_absolute() or str(path)!=name or any(part in ('..','.git','__pycache__') for part in path.parts) or name.endswith(('.pyc','.pth')):
        raise ValueError('unsafe unit payload path')
    if name not in SOURCE_FILES and not name.startswith('vendor/'):raise ValueError('unit payload name not allowed')


def verify(candidate,expected):
    candidate=Path(candidate)
    if not candidate.is_absolute() or candidate.resolve(strict=True)!=candidate:raise ValueError('canonical unit fixture required')
    raw=regular(candidate/'unit-acceptance-manifest.json',256*1024)
    if type(expected) is not str or not re.fullmatch('[0-9a-f]{64}',expected) or hashlib.sha256(raw).hexdigest()!=expected:
        raise ValueError('unit fixture manifest differs')
    manifest=decode(raw)
    if (set(manifest)!={'contract','scope','source_commit','runtime_manifest_sha256','files'} or
            manifest['contract']!='engineering-history-unit-acceptance.v1' or manifest['scope']!='isolated-hardened-unit-only' or
            type(manifest['files']) is not dict or not SOURCE_FILES<=set(manifest['files']) or not len(SOURCE_FILES)<len(manifest['files'])<=256 or
            not re.fullmatch('[0-9a-f]{40}',manifest['source_commit']) or encoded(manifest)!=raw):raise ValueError('invalid unit fixture manifest')
    files={}
    for name,sha in manifest['files'].items():
        safe_name(name);content=regular(candidate/name)
        if hashlib.sha256(content).hexdigest()!=sha:raise ValueError('unit fixture bytes differ')
        files[name]=content
        if sum(map(len,files.values()))>LIMIT:raise ValueError('unit fixture exceeds bound')
    if hashlib.sha256(files['runtime-manifest.json']).hexdigest()!=manifest['runtime_manifest_sha256']:
        raise ValueError('nested runtime manifest differs')
    return manifest,files


def build(source,vendor,destination,commit):
    source=Path(source).resolve(strict=True);destination=Path(destination)
    spec=importlib.util.spec_from_file_location('unit_runtime_package',source/'engineering/tools/rras_history/production_package.py')
    package=importlib.util.module_from_spec(spec);spec.loader.exec_module(package)
    result=package.build(source,vendor,destination,commit)
    for name in sorted(SOURCE_FILES):
        path=destination/name
        if not path.exists():
            raw=regular(source/name);path.parent.mkdir(mode=0o700,parents=True,exist_ok=True);path.write_bytes(raw)
    files={}
    for path in sorted(destination.rglob('*')):
        if path.is_dir():continue
        name=path.relative_to(destination).as_posix();safe_name(name);files[name]=hashlib.sha256(regular(path)).hexdigest()
    manifest=dict(contract='engineering-history-unit-acceptance.v1',scope='isolated-hardened-unit-only',source_commit=commit,
                  runtime_manifest_sha256=result['manifest_sha256'],files=files)
    raw=encoded(manifest);(destination/'unit-acceptance-manifest.json').write_bytes(raw)
    digest=hashlib.sha256(raw).hexdigest();verify(destination,digest)
    return dict(phase='hardened_unit_candidate_built',files=len(files),manifest_sha256=digest,
                runtime_manifest_sha256=result['manifest_sha256'],host_mutations=False,activation_authorized=False)


def emit_helper(destination):
    verifier=Path(__file__).read_text().split('\ndef build(',1)[0]
    stage=Path(__file__).with_name('stage_unit_acceptance.py').read_text()
    with Path(destination).open('x') as stream:stream.write(verifier+'\n'+stage)
    return hashlib.sha256(Path(destination).read_bytes()).hexdigest()
