"""Administrator-only absent-release installer; installs no service and runs no task."""
import argparse
import grp
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import stat
import subprocess
import tarfile

ACCOUNT='jarvis-codex-engineering'
BASE=Path('/opt/rras-engineering')
STATE=Path('/var/lib/rras-engineering')
UV_SHA='abdc39eab8b4ad341dca91f3823a23a343fae94bdb22ebdd9e91694415206f2f'


def trusted(path):
    path=Path(path).resolve(strict=True)
    for item in (path,*path.parents):
        s=item.stat()
        if s.st_uid!=0 or s.st_mode & 0o022:
            raise ValueError('root-owned non-writable trust chain required: '+str(item))
    return path


def verify_review(review, expected):
    review=Path(review)
    m=review/'manifest.json'
    if hashlib.sha256(m.read_bytes()).hexdigest()!=expected:
        raise ValueError('review manifest pin mismatch')
    files=json.loads(m.read_text())['files']
    actual={str(p.relative_to(review)) for p in review.rglob('*') if p.is_file() and p!=m}
    if actual!=set(files):raise ValueError('review inventory mismatch')
    for p in review.rglob('*'):
        if p.is_symlink() or not (p.is_file() or p.is_dir()):raise ValueError('review links/special files forbidden')
    for n,h in files.items():
        p=review/n
        if not p.resolve().is_relative_to(review.resolve()) or hashlib.sha256(p.read_bytes()).hexdigest()!=h:
            raise ValueError('review file pin mismatch')
    return files


def verify_python(path):
    path=trusted(path)
    runtime=path.parent.parent
    pin=json.loads((trusted(runtime/"runtime-pin.json")).read_text())
    if pin.get("version")!="3.13.16" or pin.get("artifact_sha256")!="f4b1bfb3c79b5bb11b8d228a12504163b4c0dab4d679828d8f5f26b6cb6ab35d" or hashlib.sha256(path.read_bytes()).hexdigest()!=pin.get("executable_sha256"):
        raise ValueError("approved runtime pin mismatch")
    for p in runtime.rglob("*"):
        if p.is_symlink() and not p.resolve().is_relative_to(runtime):raise ValueError("runtime link escapes approved tree")
        trusted(p)
    return path


def account():
    a=pwd.getpwnam(ACCOUNT)
    if a.pw_uid in (0,1000,997,65534) or a.pw_shell not in ('/usr/sbin/nologin','/sbin/nologin') or a.pw_dir!=str(STATE):
        raise ValueError('dedicated non-login account/home required')
    if len([p for p in pwd.getpwall() if p.pw_uid==a.pw_uid])!=1:
        raise ValueError('ambiguous UID')
    if set(os.getgrouplist(ACCOUNT,a.pw_gid))!={a.pw_gid}:
        raise ValueError('supplementary authority forbidden')
    if grp.getgrgid(a.pw_gid).gr_name!=ACCOUNT:raise ValueError('dedicated group required')
    return a


def install(review, expected, python, release_id):
    if os.geteuid()!=0:raise ValueError('administrator execution required')
    if not re.fullmatch(r'native-[0-9]+(?:-retry[0-9]+)?',release_id):raise ValueError('invalid release ID')
    review=trusted(review);verify_review(review,expected)
    for p in review.rglob('*'):trusted(p)
    python=verify_python(python)
    a=account()
    version=subprocess.check_output([str(python),'-I','-B','-c','import platform;print(platform.python_version())'],timeout=10,text=True).strip()
    if version!='3.13.16':raise ValueError('approved Python 3.13.16 required')
    uv=review/'build-tools/uv'
    if hashlib.sha256(uv.read_bytes()).hexdigest()!=UV_SHA:raise ValueError('uv pin mismatch')
    for parent in (BASE.parent,STATE.parent):trusted(parent)
    if BASE.exists():trusted(BASE)
    release=BASE/'releases'/release_id
    if release.exists() or release.is_symlink() or STATE.exists() or STATE.is_symlink():
        raise ValueError('release and runtime state must be absent; preserve partial/existing work')
    if not BASE.exists():
        BASE.mkdir(mode=0o755);BASE.chmod(0o755)
    if stat.S_IMODE(BASE.stat().st_mode)!=0o755:raise ValueError('existing release base mode must be reviewed 0755')
    if not (BASE/'releases').exists():
        (BASE/'releases').mkdir(mode=0o755);(BASE/'releases').chmod(0o755)
    trusted(BASE/'releases')
    if stat.S_IMODE((BASE/'releases').stat().st_mode)!=0o755:raise ValueError('release parent mode must be 0755')
    shutil.copytree(review,release)
    receipt={'schema_version':1,'release':str(release),'state':str(STATE),'review_sha256':expected,
             'uid':a.pw_uid,'gid':a.pw_gid,'state_created':False,'phase':'building',
             'services_installed':False,'credentials_provisioned':False,'tasks_run':0}
    def save():
        temp=release/'.installation-result.next'
        with temp.open('x') as stream:stream.write(json.dumps(receipt,indent=2)+'\n')
        temp.chmod(0o444)
        temp.replace(release/'installation-result.json')
    save()
    try:
        source=release/'hermes'
        source.mkdir(mode=0o755)
        with tarfile.open(release/'hermes-source.tar.gz') as t:t.extractall(source,filter='data')
        home=release/'build-home';home.mkdir(mode=0o700)
        env={'PATH':'/usr/bin:/bin','HOME':str(home),'UV_PYTHON_DOWNLOADS':'never',
             'UV_CACHE_DIR':str(home/'cache'),'UV_PROJECT_ENVIRONMENT':str(release/'venv'),
             'UV_LINK_MODE':'copy','PYTHONDONTWRITEBYTECODE':'1'}
        with (release/'dependency-build.log').open('w') as log:
            subprocess.run([str(uv),'sync','--project',str(source),'--frozen','--no-dev',
                            '--python',str(python)],env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=300)
        if not os.access(release/'venv/bin/hermes',os.X_OK) or not (release/'venv/pyvenv.cfg').is_file():
            raise ValueError('dependency build produced no complete Hermes environment')
        for p in release.rglob('*'):
            if p.is_symlink():
                trusted(p)
            elif p.is_dir():p.chmod(0o755)
            else:p.chmod(0o555 if p.stat().st_mode & 0o111 else 0o444)
        # Root may rewrite its result file; never move/reuse existing mutable state.
        STATE.mkdir(mode=0o700);os.chown(STATE,a.pw_uid,a.pw_gid)
        receipt['state_created']=True;save()
        for n in ('kanban','workspaces','repos','evidence','codex','profiles','profiles/rras-engineering'):
            p=STATE/n;p.mkdir(mode=0o700);os.chown(p,a.pw_uid,a.pw_gid)
        for src,dst in [('profile/config.yaml','config.yaml'),('profile/config.yaml','profiles/rras-engineering/config.yaml'),('codex/config.toml','codex/config.toml')]:
            p=STATE/dst;shutil.copyfile(release/src,p);p.chmod(0o600);os.chown(p,a.pw_uid,a.pw_gid)
        receipt['phase']='installed-disabled';save()
    except Exception as exc:
        receipt['phase']='failed';receipt['error']=type(exc).__name__+': '+str(exc);save();raise
    return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--review',type=Path,required=True);p.add_argument('--manifest-sha256',required=True)
    p.add_argument('--python',type=Path,required=True);p.add_argument('--release-id',required=True)
    a=p.parse_args();print(json.dumps(install(a.review,a.manifest_sha256,a.python,a.release_id),indent=2))
