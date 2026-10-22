"""Build/verify a bounded offline cross-UID acceptance payload; no installation."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat

SOURCE_FILES = tuple('engineering/tools/rras_history/'+name+'.py' for name in (
    'access','contract','documents','store','unix','interactive','interactive_cli','service_cli','host_probe','host_acceptance')) + (
    'engineering/contracts/engineering-history-v1.schema.json',) + tuple(
    'engineering/docs/engineering-history-phase1/templates/'+name+'.md' for name in ('review','checkpoint','completion'))
LIMIT=8*1024*1024


def encoded(value):return (json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode()


def decode(raw):
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('duplicate manifest key')
            result[key]=value
        return result
    return json.loads(raw,object_pairs_hook=unique)


def regular(path,maximum=4*1024*1024):
    info=path.lstat()
    if (path.resolve(strict=True)!=path or not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_size>maximum):
        raise ValueError('bounded canonical regular payload required')
    raw=path.read_bytes()
    if len(raw)>maximum:raise ValueError('payload grew beyond bound')
    return raw


def safe_name(name):
    if not isinstance(name,str):raise ValueError('manifest path required')
    p=PurePosixPath(name)
    if (p.is_absolute() or str(p)!=name or any(part in ('..','.git','__pycache__') for part in p.parts) or
            not (name in SOURCE_FILES or name.startswith('vendor/')) or name.endswith(('.pyc','.pth'))):
        raise ValueError('unsafe acceptance payload name')
    return name


def verify(candidate,expected):
    candidate=Path(candidate)
    if not candidate.is_absolute() or candidate.resolve(strict=True)!=candidate:
        raise ValueError('canonical candidate required')
    raw=regular(candidate/'acceptance-manifest.json',256*1024)
    if not re.fullmatch('[0-9a-f]{64}',expected) or hashlib.sha256(raw).hexdigest()!=expected:
        raise ValueError('acceptance manifest digest differs')
    manifest=decode(raw)
    if (set(manifest)!={'contract','scope','source_commit','files'} or
            manifest['contract']!='engineering-history-host-acceptance.v1' or manifest['scope']!='isolated-cross-uid-acceptance-only' or
            not re.fullmatch('[0-9a-f]{40}',manifest['source_commit']) or type(manifest['files']) is not dict or
            not set(SOURCE_FILES)<=set(manifest['files']) or not len(SOURCE_FILES)<len(manifest['files'])<=256):
        raise ValueError('invalid acceptance manifest')
    if encoded(manifest)!=raw:raise ValueError('canonical manifest required')
    files={}
    for name,sha in manifest['files'].items():
        safe_name(name)
        if type(sha) is not str or not re.fullmatch('[0-9a-f]{64}',sha):raise ValueError('exact payload digest required')
        content=regular(candidate/name)
        if hashlib.sha256(content).hexdigest()!=sha:raise ValueError('acceptance file digest differs')
        files[name]=content
        if sum(map(len,files.values()))>LIMIT:raise ValueError('acceptance size exceeds bound')
    return manifest,files


def build(source,vendor,destination,commit):
    source=Path(source).resolve(strict=True);vendor=Path(vendor).resolve(strict=True);destination=Path(destination)
    if not re.fullmatch('[0-9a-f]{40}',commit):raise ValueError('exact source commit required')
    files={name:regular(source/name) for name in SOURCE_FILES}
    for path in sorted(vendor.rglob('*')):
        if path.is_dir() and not path.is_symlink():continue
        name='vendor/'+path.relative_to(vendor).as_posix()
        if '__pycache__' in path.parts or path.suffix=='.pyc':continue
        safe_name(name);files[name]=regular(path)
    if not len(SOURCE_FILES)<len(files)<=256 or sum(map(len,files.values()))>LIMIT:raise ValueError('bounded vendored payload required')
    manifest=dict(contract='engineering-history-host-acceptance.v1',scope='isolated-cross-uid-acceptance-only',source_commit=commit,
                  files={name:hashlib.sha256(raw).hexdigest() for name,raw in sorted(files.items())})
    destination.mkdir(mode=0o700)
    for name,raw in files.items():
        target=destination/name;target.parent.mkdir(mode=0o700,parents=True,exist_ok=True);target.write_bytes(raw)
    raw=encoded(manifest);(destination/'acceptance-manifest.json').write_bytes(raw)
    return dict(phase='history_acceptance_candidate_built',files=len(files),manifest_sha256=hashlib.sha256(raw).hexdigest(),root_mutations=False)


def emit_helper(destination):
    verifier=Path(__file__).read_text().split('\ndef build(',1)[0]
    bootstrap=Path(__file__).with_name('stage_history_acceptance.py').read_text()
    destination=Path(destination)
    with destination.open('x') as stream:stream.write(verifier+'\n'+bootstrap)
    return hashlib.sha256(destination.read_bytes()).hexdigest()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',required=True);parser.add_argument('--vendor',required=True)
    parser.add_argument('--destination',required=True);parser.add_argument('--source-commit',required=True)
    args=parser.parse_args()
    print(json.dumps(build(args.source,args.vendor,args.destination,args.source_commit)))
