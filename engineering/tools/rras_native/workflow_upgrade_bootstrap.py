"""Verify and stage exact reviewed deployment tools; never import user-owned code.

This standalone file must itself be reviewed and hash-pinned by the operator
before sudo. It installs code only, without running any staging/activation tool.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import traceback

RELEASES=Path('/opt/rras-engineering/releases')
SOURCE=Path('/srv/git/jarvis')
FILES=('stage_workflow_upgrade.py','activate_workflow_upgrade.py')
SOURCE_PREFIX='engineering/tools/rras_native/'
LIMIT=1024*1024


def sha(raw):return hashlib.sha256(raw).hexdigest()
def encoded(value):return (json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
def decode(raw):
    def unique(pairs):
        result={}
        for k,v in pairs:
            if k in result:raise ValueError('duplicate key')
            result[k]=v
        return result
    return json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite JSON')))


def read(path,limit=LIMIT):
    path=Path(path)
    if not path.is_absolute() or path.resolve(strict=True)!=path:raise ValueError('canonical input required')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_size>limit:raise ValueError('bounded regular input required')
        with os.fdopen(os.dup(fd),'rb') as stream:raw=stream.read(limit+1)
        if len(raw)>limit:raise ValueError('input exceeds bound')
        return raw
    finally:os.close(fd)


def protected(path):
    path=Path(path)
    for item in (path,*path.parents):
        info=item.lstat()
        if stat.S_ISLNK(info.st_mode) or info.st_uid!=0 or info.st_mode&0o022:raise ValueError('root-protected destination required')
    return path


def administrator():
    if os.getuid()!=0 or os.geteuid()!=0:raise ValueError('administrator staging required')


def sync(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


def write(path,raw,mode):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
    with os.fdopen(fd,'wb') as stream:
        os.fchmod(stream.fileno(),mode);stream.write(raw);stream.flush();os.fsync(stream.fileno())
    sync(path.parent)


def verify(candidate,expected):
    candidate=Path(candidate)
    if not isinstance(expected,str) or not re.fullmatch('[0-9a-f]{64}',expected):raise ValueError('exact manifest digest required')
    raw=read(candidate/'deployment-tools-manifest.json',65536)
    if sha(raw)!=expected:raise ValueError('manifest digest changed')
    manifest=decode(raw)
    if (set(manifest)!={'schema_version','scope','source_commit','files'} or manifest['schema_version']!=1 or
        manifest['scope']!='workflow-upgrade-tools-only' or not isinstance(manifest['source_commit'],str) or
        not re.fullmatch('[0-9a-f]{40}',manifest['source_commit']) or set(manifest['files'])!=set(FILES)):raise ValueError('reviewed tools manifest required')
    payload={}
    for name,digest in manifest['files'].items():
        if PurePosixPath(name).name!=name or not isinstance(digest,str) or not re.fullmatch('[0-9a-f]{64}',digest):raise ValueError('exact tool digest required')
        content=read(candidate/name)
        if sha(content)!=digest:raise ValueError('deployment tool changed')
        compile(content,name,'exec') # Parse only; never evaluate/import candidate.
        payload[name]=content
    return manifest,raw,payload


def git(args):
    return subprocess.run(['/usr/bin/git','--no-replace-objects','-c','safe.directory='+str(SOURCE),'-c','core.hooksPath=/dev/null','-C',str(SOURCE),*args],
        stdin=subprocess.DEVNULL,capture_output=True,check=True,timeout=30,
        env={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','LANG':'C.UTF-8'}).stdout


def stage(candidate,expected):
    administrator();manifest,raw,payload=verify(candidate,expected)
    # Re-read commit bytes from canonical Git as data. No candidate code is loaded
    # even to check its protection requirements or source ancestry.
    git(['merge-base','--is-ancestor',manifest['source_commit'],'main'])
    for name,content in payload.items():
        if git(['show',manifest['source_commit']+':'+SOURCE_PREFIX+name])!=content:raise ValueError('tool differs from reviewed commit')
    protected(RELEASES)
    target=RELEASES/('workflow-upgrade-tools-'+expected[:12])
    if target.exists() or target.is_symlink():raise ValueError('tools destination exists; preserve, never adopt or retry')
    target.mkdir(mode=0o755);target.chmod(0o755);sync(RELEASES)
    try:
        write(target/'started.json',encoded({'manifest_sha256':expected,'source_commit':manifest['source_commit']}),0o444)
        for name,content in payload.items():write(target/name,content,0o444)
        write(target/'deployment-tools-manifest.json',raw,0o444)
        answer={'phase':'workflow_upgrade_tools_staged','release':str(target),'manifest_sha256':expected,
            'source_commit':manifest['source_commit'],'services_changed':False,'configuration_changed':False,
            'production_journal_changed':False,'activation_authorized':False,'api_calls':0}
        write(target/'complete.json',encoded(answer),0o444);sync(target);return answer
    except BaseException:
        try:write(target/'staging-error.txt',traceback.format_exc().encode()[:65536],0o600)
        except OSError:pass
        raise


def inspect(release,expected):
    administrator();release=Path(release)
    if release.parent!=RELEASES or release.name!='workflow-upgrade-tools-'+expected[:12]:raise ValueError('exact tools release required')
    protected(release)
    manifest,raw,payload=verify(release,expected)
    for path in (release/'started.json',release/'complete.json',release/'deployment-tools-manifest.json',*[release/name for name in FILES]):
        protected(path)
        if stat.S_IMODE(path.stat().st_mode)!=0o444:raise ValueError('installed tool mode changed')
    start=decode(read(release/'started.json',65536))
    if start!={'manifest_sha256':expected,'source_commit':manifest['source_commit']}:raise ValueError('tool start identity changed')
    answer=decode(read(release/'complete.json',65536))
    if (answer['manifest_sha256']!=expected or answer['source_commit']!=manifest['source_commit'] or
        answer['release']!=str(release) or answer['phase']!='workflow_upgrade_tools_staged'):raise ValueError('tool completion identity changed')
    return dict(answer,phase='workflow_upgrade_tools_verified',automatic_retry=False)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('verify-only','stage','inspect'))
    p.add_argument('--candidate');p.add_argument('--release');p.add_argument('--manifest-sha256',required=True);args=p.parse_args(argv)
    try:
        if args.action=='verify-only':
            manifest,raw,payload=verify(args.candidate,args.manifest_sha256)
            answer={'phase':'workflow_upgrade_tools_candidate_verified','files':len(payload),'root_mutations':False,'services_changed':False}
        elif args.action=='stage':answer=stage(args.candidate,args.manifest_sha256)
        else:answer=inspect(args.release,args.manifest_sha256)
    except (ValueError,OSError,KeyError,TypeError,SyntaxError,subprocess.SubprocessError):p.exit(1,'Tools bootstrap refused; preserve existing evidence. No automatic retry or activation.\n')
    print(json.dumps(answer))

if __name__=='__main__':main()
