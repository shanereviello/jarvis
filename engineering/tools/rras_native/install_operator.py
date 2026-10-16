"""Fresh, inactive operator-source installation. No service/config/credential writes.

Root-only CLI with fixed allocations and manifest pin. Resume/rollback use inode
receipts; a path created without its receipt is ambiguous and is never adopted.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile

CANDIDATE=Path('/opt/rras-operator-install-review-20261016-01/candidate')
MANIFEST='c8f878a8082917cbd0c35a4f95395390e35186cec37114251dac60d9f47141ae'
JOURNAL=Path('/var/lib/rras-operator-install-70027c9e9534')
LAYOUT={'release':('/opt/rras-engineering/releases/operator-70027c9e9534',0,0,0o755),
        'control':('/var/lib/rras-coding-control',0,0,0o700),
        'jobs':('/opt/rras-coding-jobs',0,0,0o755),
        'workers':('/var/lib/rras-coding-tasks',996,996,0o700)}


def encoded(obj):return (json.dumps(obj,sort_keys=True,separators=(',',':'))+'\n').encode()
def digest(data):return hashlib.sha256(data).hexdigest()

def protected(path):
    p=Path(path)
    for item in (p,*p.parents):
        s=item.lstat()
        if stat.S_ISLNK(s.st_mode) or s.st_uid!=0 or s.st_mode&0o022:raise ValueError('unprotected administrator path')
    return p


def guards():
    if os.geteuid()!=0:raise ValueError('administrator invocation required')
    def command(*args):
        return subprocess.run(args,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'},stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=15)
    r=command('/usr/bin/systemctl','show','rras-coding-task.service','-p','LoadState','--value')
    if r.returncode!=0 or r.stdout.strip()!='not-found':raise ValueError('worker slot must be empty')
    if command('/usr/bin/pgrep','-u','996').returncode!=1:raise ValueError('worker identity busy or ambiguous')
    r=command('/usr/bin/systemctl','is-enabled','jarvis-codex-reconcile.timer')
    if r.returncode!=1 or r.stdout.strip()!='disabled':raise ValueError('legacy timer must remain disabled')
    for prop,expected in [('ActiveState','inactive'),('SubState','dead')]:
        r=command('/usr/bin/systemctl','show','jarvis-codex-reconcile.timer','-p',prop,'--value')
        if r.returncode!=0 or r.stdout.strip()!=expected:raise ValueError('legacy timer state ambiguous')


def payload():
    manifest_path=protected(CANDIDATE/'manifest.json')
    if not stat.S_ISREG(manifest_path.stat().st_mode) or manifest_path.stat().st_size>1024*1024:raise ValueError('regular bounded manifest required')
    raw=manifest_path.read_bytes()
    if (CANDIDATE/'manifest.json').is_symlink() or digest(raw)!=MANIFEST:raise ValueError('candidate manifest changed')
    manifest=json.loads(raw);files={}
    for name,expected in manifest['files'].items():
        if Path(name).name!=name:raise ValueError('invalid candidate member')
        p=protected(CANDIDATE/name)
        if not stat.S_ISREG(p.lstat().st_mode) or p.is_symlink() or not p.is_file() or p.stat().st_size>2*1024*1024:raise ValueError('invalid source member')
        data=p.read_bytes()
        if len(data)>2*1024*1024 or digest(data)!=expected:raise ValueError('candidate member changed')
        files[name]=data
    files['manifest.json']=raw
    return files


def write_record(name,data):
    target=JOURNAL/name
    if target.exists() or target.is_symlink():raise ValueError('journal record already exists')
    fd,tmp=tempfile.mkstemp(prefix='.record-',dir=JOURNAL)
    try:
        with os.fdopen(fd,'wb') as f:f.write(encoded(data));f.flush();os.fsync(f.fileno())
        os.link(tmp,target)
        sync_dir(JOURNAL)
    finally:os.unlink(tmp)


def sync_dir(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


def load_record(name):
    p=JOURNAL/name
    if p.is_symlink():raise ValueError('journal symlink refused')
    if not p.exists():return None
    protected(p)
    return json.loads(p.read_bytes())


def identity(path):
    s=Path(path).lstat()
    return {'device':s.st_dev,'inode':s.st_ino,'uid':s.st_uid,'gid':s.st_gid,
            'mode':stat.S_IMODE(s.st_mode),'kind':stat.S_IFMT(s.st_mode)}


def matches(path,record):
    if identity(path)!=record['identity']:raise ValueError('allocation identity changed: '+str(path))
    if 'sha256' in record and digest(Path(path).read_bytes())!=record['sha256']:raise ValueError('installed content changed: '+str(path))


def allocate(key,path,uid,gid,mode,data=None):
    path=Path(path);receipt=load_record(key+'.allocated.json')
    if receipt:
        matches(path,receipt);return
    protected(path.parent)
    if path.exists() or path.is_symlink():raise ValueError('unrecorded allocation; preserve and inspect: '+str(path))
    if not load_record(key+'.intent.json'):write_record(key+'.intent.json',{'path':str(path)})
    if data is None:path.mkdir(mode=mode)
    else:
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
        with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
    os.chown(path,uid,gid,follow_symlinks=False);path.chmod(mode);sync_dir(path.parent)
    record={'path':str(path),'identity':identity(path)}
    if data is not None:record['sha256']=digest(data)
    write_record(key+'.allocated.json',record)


def check_header():
    protected(JOURNAL)
    if stat.S_IMODE(JOURNAL.stat().st_mode)!=0o700:raise ValueError('private journal required')
    if load_record('header.json')!={'schema_version':1,'manifest_sha256':MANIFEST,'layout':LAYOUT_JSON()}:
        raise ValueError('journal mismatch; preserve it')
    if list(JOURNAL.glob('.record-*')):raise ValueError('interrupted journal write; preserve temporary records')


def LAYOUT_JSON():return {k:list(v) for k,v in LAYOUT.items()}


def expected(files):
    release=Path(LAYOUT['release'][0])
    rows=[('release',release,0,0,0o755,None)]
    rows += [('file-'+name,release/name,0,0,0o444,data) for name,data in sorted(files.items())]
    rows += [(k,Path(p),u,g,m,None) for k,(p,u,g,m) in LAYOUT.items() if k!='release']
    return rows


def verify(rows,complete=True,rolling=False):
    for key,path,*_ in rows:
        r=load_record(key+'.allocated.json')
        if r:
            if rolling and load_record(key+'.removing.json') and not path.exists() and not path.is_symlink():continue
            matches(path,r)
        elif path.exists() or path.is_symlink():raise ValueError('unrecorded allocation; preserve and inspect: '+str(path))
        elif complete:raise ValueError('incomplete installation')
    release=Path(LAYOUT['release'][0])
    known={p.name for _,p,*_ in rows if p.parent==release and p.exists() and load_record('file-'+p.name+'.allocated.json')}
    if release.exists() and {p.name for p in release.iterdir()}!=known:raise ValueError('unexpected release contents')
    for key in ('control','jobs','workers'):
        p=Path(LAYOUT[key][0])
        if p.exists() and any(p.iterdir()):raise ValueError('runtime records exist; preserve them')


def run(action):
    if action=='inspect':
        if os.geteuid()!=0:raise ValueError('administrator inspection required')
        check_header();rows=expected(payload());status=[]
        for key,path,*_ in rows:
            record=load_record(key+'.allocated.json');exists=path.exists() or path.is_symlink()
            status.append({'key':key,'path':str(path),'recorded':bool(record),'present':exists,
                           'identity':identity(path) if exists else None})
        return {'scope':'operator-install-inspection','allocations':status,'host_changes':False}
    guards();files=payload();rows=expected(files)
    if action=='install':
        protected(JOURNAL.parent)
        if JOURNAL.exists() or JOURNAL.is_symlink():raise ValueError('journal exists; use inspect/resume, never overwrite')
        for _,path,*_ in rows:
            if path.exists() or path.is_symlink():raise ValueError('pre-existing allocation refused')
        JOURNAL.mkdir(mode=0o700);JOURNAL.chmod(0o700);sync_dir(JOURNAL.parent)
        write_record('header.json',{'schema_version':1,'manifest_sha256':MANIFEST,'layout':LAYOUT_JSON()})
    check_header()
    with (JOURNAL/'lock').open('a+b') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if load_record('rolled-back.json'):raise ValueError('installation rolled back; preserve journal')
        if action!='rollback' and load_record('rollback-started.json'):raise ValueError('rollback began; do not resume installation')
        if action in ('install','resume'):
            verify(rows,complete=False)
            for row in rows:allocate(*row)
            verify(rows)
            if not load_record('complete.json'):write_record('complete.json',{'status':'complete','execution_authorized':False,'service_activation':False})
        elif action=='check':verify(rows)
        elif action=='rollback':
            verify(rows,complete=False,rolling=True)  # Check every remaining allocation before deleting anything.
            if not load_record('rollback-started.json'):write_record('rollback-started.json',{'status':'rollback-started'})
            for key,path,*_ in reversed(rows):
                if load_record(key+'.allocated.json'):
                    if not load_record(key+'.removing.json'):write_record(key+'.removing.json',{'path':str(path)})
                    if path.exists() or path.is_symlink():
                        path.rmdir() if path.is_dir() else path.unlink()
                        sync_dir(path.parent)
            write_record('rolled-back.json',{'status':'rolled-back','journal_retained':True})
        else:raise ValueError('unknown action')
    return {'scope':'inactive-operator-source-install','action':action,'success':True,'journal':str(JOURNAL),'paid_execution_authorized':False,'services_modified':False}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--action',choices=('install','resume','check','rollback','inspect'),required=True)
    args=p.parse_args();print(json.dumps(run(args.action)))
