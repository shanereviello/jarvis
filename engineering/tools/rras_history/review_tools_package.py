"""Committed-source offline package for passive review export and document intake.

Build and verify only. No privileged installation, wrapper or service changes.
"""
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import re
import stat
import subprocess

LIMIT=12*1024*1024
MANIFEST='release-manifest.json'
SOURCE_FILES=set('engineering/tools/rras_history/'+name+'.py' for name in (
    'contract','documents','unix','link_delivery','managed_sync','managed_link','review_document_link',
    'review_document_export','review_document_cli','review_export_cli','review_tools_package','review_tools_entry'))|set(
    'engineering/contracts/'+name for name in ('engineering-history-v1.schema.json','engineering-managed-export-v1.schema.json'))|set(
    'engineering/docs/engineering-history-phase1/templates/'+name+'.md' for name in ('review','checkpoint','completion'))


def encoded(value):return (json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode()


def decode(raw):
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('duplicate package member')
            result[key]=value
        return result
    return json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('invalid JSON number')))


def regular(path,limit=4*1024*1024):
    path=Path(path)
    if not path.is_absolute() or path.resolve(strict=True)!=path:raise ValueError('canonical package input required')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_size>limit:raise ValueError('bounded regular package input required')
        with os.fdopen(os.dup(fd),'rb') as stream:raw=stream.read(limit+1)
        if len(raw)>limit:raise ValueError('package input exceeds bound')
        return raw
    finally:os.close(fd)


def safe_name(name):
    if type(name) is not str:raise ValueError('package path required')
    path=PurePosixPath(name)
    if (path.is_absolute() or str(path)!=name or any(p in ('..','.git','__pycache__') for p in path.parts) or
            name.endswith(('.pyc','.pth')) or (name not in SOURCE_FILES and not name.startswith('vendor/'))):
        raise ValueError('unsafe package path')


def verify(candidate,expected):
    candidate=Path(candidate)
    if not candidate.is_absolute() or candidate.resolve(strict=True)!=candidate:raise ValueError('canonical candidate required')
    raw=regular(candidate/MANIFEST,256*1024)
    if type(expected) is not str or not re.fullmatch('[0-9a-f]{64}',expected) or hashlib.sha256(raw).hexdigest()!=expected:
        raise ValueError('package manifest changed')
    manifest=decode(raw)
    if (type(manifest) is not dict or set(manifest)!={'contract','scope','source_commit','files'} or encoded(manifest)!=raw or
            manifest['contract']!='engineering-review-tools.v1' or manifest['scope']!='passive-private-export-intake' or
            type(manifest['source_commit']) is not str or not re.fullmatch('[0-9a-f]{40}',manifest['source_commit']) or
            type(manifest['files']) is not dict or not SOURCE_FILES<set(manifest['files']) or len(manifest['files'])>300):
        raise ValueError('review tools manifest invalid')
    files={};total=0
    for name,digest in manifest['files'].items():
        safe_name(name)
        if type(digest) is not str or not re.fullmatch('[0-9a-f]{64}',digest):raise ValueError('member digest required')
        raw=regular(candidate/name);total+=len(raw)
        if total>LIMIT or hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('review tools payload changed')
        files[name]=raw
    return manifest,files


def build(source,vendor,destination,commit):
    source=Path(source).resolve(strict=True);vendor=Path(vendor).resolve(strict=True);destination=Path(destination)
    if type(commit) is not str or not re.fullmatch('[0-9a-f]{40}',commit):raise ValueError('exact source commit required')
    def git(*args):return subprocess.check_output(['/usr/bin/git','-C',str(source),*args],stderr=subprocess.PIPE,
        env={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','LANG':'C.UTF-8','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null'},timeout=30)
    if git('rev-parse','HEAD').decode().strip()!=commit:raise ValueError('exact current source commit required')
    files={name:git('show',commit+':'+name) for name in SOURCE_FILES}
    for path in sorted(vendor.rglob('*')):
        if path.is_dir() and not path.is_symlink():continue
        if '__pycache__' in path.parts or path.suffix=='.pyc':continue
        name='vendor/'+path.relative_to(vendor).as_posix();safe_name(name);files[name]=regular(path)
    manifest={'contract':'engineering-review-tools.v1','scope':'passive-private-export-intake','source_commit':commit,
        'files':{name:hashlib.sha256(raw).hexdigest() for name,raw in sorted(files.items())}}
    # Validate bounds before creating the destination; do not leave oversized candidates.
    if len(files)>300 or sum(map(len,files.values()))>LIMIT or not SOURCE_FILES<set(files):raise ValueError('package bounds exceeded')
    if not destination.is_absolute() or destination.parent.resolve(strict=True)!=destination.parent:raise ValueError('canonical destination required')
    destination.mkdir(mode=0o700)
    for name,raw in files.items():
        path=destination/name;path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        with path.open('xb') as stream:os.fchmod(stream.fileno(),0o600);stream.write(raw)
    raw=encoded(manifest)
    with (destination/MANIFEST).open('xb') as stream:os.fchmod(stream.fileno(),0o600);stream.write(raw)
    sha=hashlib.sha256(raw).hexdigest();verify(destination,sha)
    return {'candidate':str(destination),'manifest_sha256':sha,'files':len(files),'source_commit':commit,
            'root_mutations':False,'installed':False}
