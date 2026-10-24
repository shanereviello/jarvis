"""Pinned production export tools and exact one-work export plan validation."""
import hashlib
import json
from pathlib import Path,PurePosixPath
import re
import stat

SOURCE=Path('/var/lib/rras-workflow/journal')
JOURNALS=Path('/var/lib/rras-history-exports')
HANDOFFS=Path('/var/lib/rras-history-handoffs')
PYTHON=Path('/opt/rras-engineering/releases/native-10/venv/bin/python')
LIMIT=8*1024*1024
SOURCE_FILES=set('engineering/tools/rras_history/'+name+'.py' for name in ('contract','managed_link','managed_export_entry'))|set(
    'engineering/tools/rras_native/'+name+'.py' for name in ('workflow_records','workflow_journal','engineering_export'))|set(
    'engineering/contracts/'+name for name in ('engineering-history-v1.schema.json','engineering-managed-export-v1.schema.json','workflow-v1.schema.json'))


def encoded(value):return (json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode()


def decode(raw):
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('duplicate export JSON key')
            result[key]=value
        return result
    return json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('invalid number')))


def regular(path,limit=4*1024*1024):
    info=path.lstat()
    if path.resolve(strict=True)!=path or not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_size>limit:
        raise ValueError('bounded canonical regular export input required')
    raw=path.read_bytes()
    if len(raw)>limit:raise ValueError('export input grew beyond bound')
    return raw


def safe_name(name):
    if type(name) is not str:raise ValueError('export payload name required')
    p=PurePosixPath(name)
    if p.is_absolute() or str(p)!=name or any(part in ('..','.git','__pycache__') for part in p.parts) or name.endswith(('.pyc','.pth')):
        raise ValueError('unsafe export payload path')
    if name not in SOURCE_FILES and not name.startswith('vendor/'):raise ValueError('unlisted export payload')


def validate_plan(plan):
    keys={'capture_id','contract','scope','journal_id','work_item_id','repository_id','source_work_sha256','baseline','allowed_paths','reader_uid'}
    if (type(plan) is not dict or set(plan)!=keys or plan['contract']!='engineering-production-export.v1' or
            plan['scope']!='one-work-revision-allowlisted-export-only' or type(plan['reader_uid']) is not int or plan['reader_uid']!=1000):
        raise ValueError('exact passive export plan required')
    for key,pattern in (('capture_id','[0-9a-f]{32}'),('journal_id','[A-Za-z0-9][A-Za-z0-9_.-]{0,95}'),('work_item_id','wrk_[0-9a-f]{32}'),
                        ('repository_id','[A-Za-z0-9][A-Za-z0-9_.-]{0,95}'),('source_work_sha256','[0-9a-f]{64}')):
        if type(plan[key]) is not str or not re.fullmatch(pattern,plan[key]):raise ValueError('exact export identity required')
    baseline=plan['baseline']
    if baseline is not None:
        if (type(baseline) is not dict or set(baseline)!={'ref','commit'} or type(baseline['ref']) is not str or not 1<=len(baseline['ref'])<=512 or
                type(baseline['commit']) is not str or not re.fullmatch('[0-9a-f]{40}|[0-9a-f]{64}',baseline['commit'])):
            raise ValueError('exact export baseline required')
    paths=plan['allowed_paths']
    if type(paths) is not list or len(paths)>128 or any(type(name) is not str for name in paths) or len(set(paths))!=len(paths):
        raise ValueError('bounded export scope required')
    for name in paths:
        p=PurePosixPath(name)
        if not name or name=='.' or p.is_absolute() or str(p)!=name or any(part in ('..','.git') for part in p.parts) or '\\' in name or '\0' in name:
            raise ValueError('canonical relative export scope required')
    if len(encoded(plan))>32*1024:raise ValueError('bounded export plan required')
    return plan


def verify(candidate,expected):
    candidate=Path(candidate)
    if not candidate.is_absolute() or candidate.resolve(strict=True)!=candidate:raise ValueError('canonical export tools required')
    raw=regular(candidate/'export-tools-manifest.json',256*1024)
    if type(expected) is not str or not re.fullmatch('[0-9a-f]{64}',expected) or hashlib.sha256(raw).hexdigest()!=expected:
        raise ValueError('export tools manifest differs')
    manifest=decode(raw)
    if (set(manifest)!={'contract','source_commit','files'} or manifest['contract']!='engineering-export-tools.v1' or
            not re.fullmatch('[0-9a-f]{40}',manifest['source_commit']) or type(manifest['files']) is not dict or
            not SOURCE_FILES<set(manifest['files']) or len(manifest['files'])>256 or encoded(manifest)!=raw):
        raise ValueError('export tools manifest invalid')
    files={}
    for name,sha in manifest['files'].items():
        safe_name(name);raw=regular(candidate/name)
        if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('export tool bytes differ')
        files[name]=raw
        if sum(map(len,files.values()))>LIMIT:raise ValueError('export tools exceed bound')
    return manifest,files


def build(source,vendor,destination,commit):
    source=Path(source).resolve(strict=True);vendor=Path(vendor).resolve(strict=True);destination=Path(destination)
    if not re.fullmatch('[0-9a-f]{40}',commit):raise ValueError('exact export source commit required')
    files={name:regular(source/name) for name in SOURCE_FILES}
    for path in sorted(vendor.rglob('*')):
        if path.is_dir() and not path.is_symlink():continue
        if '__pycache__' in path.parts or path.suffix=='.pyc':continue
        name='vendor/'+path.relative_to(vendor).as_posix();safe_name(name);files[name]=regular(path)
    manifest={'contract':'engineering-export-tools.v1','source_commit':commit,
              'files':{name:hashlib.sha256(raw).hexdigest() for name,raw in sorted(files.items())}}
    destination.mkdir(mode=0o700)
    for name,raw in files.items():
        path=destination/name;path.parent.mkdir(mode=0o700,parents=True,exist_ok=True);path.write_bytes(raw)
    raw=encoded(manifest);(destination/'export-tools-manifest.json').write_bytes(raw);sha=hashlib.sha256(raw).hexdigest();verify(destination,sha)
    return {'manifest_sha256':sha,'files':len(files),'source_commit':commit,'root_mutations':False}


def emit_helper(destination):
    prefix=Path(__file__).read_text().split('\ndef build(',1)[0]
    stage=Path(__file__).with_name('stage_managed_export.py').read_text()
    with Path(destination).open('x') as stream:stream.write(prefix+'\n'+stage)
    return hashlib.sha256(Path(destination).read_bytes()).hexdigest()
