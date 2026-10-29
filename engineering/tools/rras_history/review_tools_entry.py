"""Stdlib manifest gate before loading packaged passive review commands."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path,PurePosixPath
import re
import stat
import sys


def read(root,name):
    path=root/name
    if path.resolve(strict=True)!=path:raise ValueError('canonical package member required')
    if os.geteuid()==0:
        for item in (path,*path.parents):
            info=item.lstat()
            if info.st_uid!=0 or stat.S_ISLNK(info.st_mode) or info.st_mode&0o022:raise ValueError('protected package required')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_size>4*1024*1024:raise ValueError('bounded package member required')
        with os.fdopen(os.dup(fd),'rb') as stream:raw=stream.read(4*1024*1024+1)
        if len(raw)>4*1024*1024:raise ValueError('package member exceeds bound')
        return raw
    finally:os.close(fd)


def run(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest-sha256',required=True)
    parser.add_argument('mode',choices=('export','intake'))
    parser.add_argument('arguments',nargs=argparse.REMAINDER)
    args=parser.parse_args(argv)
    root=Path(__file__).resolve().parents[3]
    raw=read(root,'release-manifest.json')
    if not re.fullmatch('[0-9a-f]{64}',args.manifest_sha256) or hashlib.sha256(raw).hexdigest()!=args.manifest_sha256:
        raise ValueError('pinned package manifest changed')
    manifest=json.loads(raw)
    if (manifest.get('contract')!='engineering-review-tools.v1' or manifest.get('scope')!='passive-private-export-intake' or
            type(manifest.get('files')) is not dict or not 1<=len(manifest['files'])<=300):raise ValueError('bounded passive package required')
    total=0
    for name,digest in manifest['files'].items():
        p=PurePosixPath(name)
        if (p.is_absolute() or str(p)!=name or '..' in p.parts or not name.startswith(('engineering/','vendor/')) or
                name.endswith(('.pyc','.pth')) or '__pycache__' in p.parts):raise ValueError('unsafe package member')
        value=read(root,name);total+=len(value)
        if total>12*1024*1024 or hashlib.sha256(value).hexdigest()!=digest:raise ValueError('pinned package payload changed')
    name='engineering/tools/rras_history/review_'+('export_cli' if args.mode=='export' else 'document_cli')+'.py'
    if name not in manifest['files'] or 'engineering/tools/rras_history/review_tools_entry.py' not in manifest['files']:
        raise ValueError('packaged entrypoint absent')
    sys.path.insert(0,str(root/'vendor'))
    spec=importlib.util.spec_from_file_location('pinned_review_command',root/name)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);module.main(args.arguments)


if __name__=='__main__':
    try:run()
    except (ValueError,TypeError,KeyError,OSError):
        sys.stderr.write('Pinned review tools refused. Preserve evidence; no automatic retry.\n');raise SystemExit(1)
