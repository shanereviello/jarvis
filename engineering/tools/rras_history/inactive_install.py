"""Reviewed additive inactive history installation. No service start or enable.

Appended to a stdlib-only pinned runtime verifier by install_package.py. Never
imports code from a caller-writable candidate as root. Partial failures retain all
evidence; no automatic retry, account adoption, rollback or database overwrite.
"""
import argparse
import grp
import os
import pwd
import sqlite3
import subprocess
import sys
import traceback

ACCOUNT='rras-history'
STORE=Path('/var/lib/rras-engineering-history')
CONFIG=Path('/etc/rras-engineering-history')
UNIT='rras-engineering-history.service'
UNIT_FILE=Path('/etc/systemd/system')/UNIT
WRAPPER=Path('/usr/local/bin/rras-history-client')
RUNTIME=Path('/run/rras-engineering-history')
JOURNALS=Path('/var/lib/rras-history-installations')
PYTHON=Path('/opt/rras-engineering/releases/native-10/venv/bin/python')
ENV={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','LANG':'C.UTF-8'}


def protected(path):
    for item in (path,*path.parents):
        info=item.lstat()
        if item.is_symlink() or info.st_uid!=0 or info.st_mode&0o022:
            raise ValueError('root-owned protected path required')


def absent(path):
    if path.exists() or path.is_symlink():raise ValueError('preserve existing installation path')


def write_new(path,raw,mode=0o600,uid=0,gid=0):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
    with os.fdopen(fd,'wb') as stream:
        os.fchmod(stream.fileno(),mode);os.fchown(stream.fileno(),uid,gid)
        stream.write(raw);stream.flush();os.fsync(stream.fileno())
    fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


def mkdir_new(path,mode=0o700,uid=0,gid=0):
    path.mkdir(mode=mode);os.chown(path,uid,gid);os.chmod(path,mode)


def command(argv):
    return subprocess.run(argv,stdin=subprocess.DEVNULL,capture_output=True,env=ENV,timeout=30)


def status():
    result=command(['/usr/bin/systemctl','show',UNIT,'--property=LoadState,ActiveState,MainPID,UnitFileState'])
    if result.returncode:raise ValueError('cannot establish history unit state')
    return dict(line.split('=',1) for line in result.stdout.decode().splitlines() if '=' in line)


def preflight(candidate,expected):
    if os.getuid()!=0 or os.geteuid()!=0:raise ValueError('explicit administrator invocation required')
    manifest,files=verify(candidate,expected)
    plan=decode(files['deployment/install-plan.json'])
    if plan['backup_status']!='deferred-by-operator-2026-10-23-no-verified-recovery':
        raise ValueError('backup decision differs')
    release=Path(manifest['release']);journal=JOURNALS/release.name
    for directory in (release.parent,STORE.parent,CONFIG.parent,UNIT_FILE.parent,WRAPPER.parent,RUNTIME.parent):protected(directory)
    for executable in (PYTHON.parent,PYTHON.resolve(strict=True),Path('/usr/bin/systemctl'),Path('/usr/bin/setpriv'),
                       Path('/usr/bin/unshare'),Path('/usr/sbin/useradd'),Path('/usr/sbin/groupadd')):
        protected(executable)
    if JOURNALS.exists():protected(JOURNALS)
    for path in (release,STORE,CONFIG,UNIT_FILE,WRAPPER,RUNTIME,journal):absent(path)
    for lookup in (pwd.getpwnam,grp.getgrnam):
        try:lookup(ACCOUNT)
        except KeyError:continue
        raise ValueError('history identity already exists; do not adopt')
    state=status()
    if state.get('LoadState')!='not-found' or state.get('MainPID','0')!='0' or state.get('ActiveState') not in ('inactive','failed'):
        raise ValueError('existing history unit refused')
    return manifest,files,journal


class Install:
    def __init__(self,journal):self.journal=journal;self.step=0
    def run(self,argv,tag):
        self.step+=1
        write_new(self.journal/f'{self.step:02d}-{tag}-intent.json',encoded({'argv':argv}))
        result=command(argv)
        write_new(self.journal/f'{self.step:02d}-{tag}-stdout',result.stdout)
        write_new(self.journal/f'{self.step:02d}-{tag}-stderr',result.stderr)
        if result.returncode:raise ValueError('installation command failed; preserve private diagnostic')
        return result


def install(candidate,expected,*,check_only=False):
    manifest,files,journal=preflight(candidate,expected)
    if check_only:return {'phase':'inactive_history_preflight_passed','mutations':False,'activation_authorized':False}
    os.umask(0o077)
    if not JOURNALS.exists():mkdir_new(JOURNALS)
    mkdir_new(journal)
    write_new(journal/'intent.json',encoded({'manifest_sha256':expected,'source_commit':manifest['source_commit'],
                'backup_status':'deferred-by-operator-2026-10-23-no-verified-recovery','activation_authorized':False}))
    operation=Install(journal)
    try:
        operation.run(['/usr/sbin/groupadd','--system',ACCOUNT],'group-create')
        operation.run(['/usr/sbin/useradd','--system','--gid',ACCOUNT,'--no-user-group','--no-create-home',
                       '--home-dir','/nonexistent','--shell','/usr/sbin/nologin','--no-log-init','--password','!',ACCOUNT],'account-create')
        user=pwd.getpwnam(ACCOUNT);group=grp.getgrnam(ACCOUNT)
        if (user.pw_uid in (0,996,997,1000) or user.pw_uid<1 or user.pw_gid!=group.gr_gid or group.gr_mem or
                user.pw_shell!='/usr/sbin/nologin' or user.pw_dir!='/nonexistent' or
                any(other.pw_gid==group.gr_gid and other.pw_name!=ACCOUNT for other in pwd.getpwall())):
            raise ValueError('dedicated identity differs')
        write_new(journal/'identity.json',encoded({'uid':user.pw_uid,'gid':group.gr_gid}))
        release=Path(manifest['release']);mkdir_new(release,0o755)
        for name,raw in sorted(files.items()):
            path=release/name
            for parent in reversed(path.relative_to(release).parents):
                if parent==Path('.'):continue
                directory=release/parent
                if not directory.exists():mkdir_new(directory,0o755)
            write_new(path,raw,0o444)
        write_new(release/'runtime-manifest.json',encoded(manifest),0o444)
        verify(release,expected)
        mkdir_new(CONFIG,0o750,0,group.gr_gid)
        write_new(CONFIG/'access-policy.json',files['deployment/access-policy.json'],0o640,0,group.gr_gid)
        mkdir_new(STORE,0o700,user.pw_uid,group.gr_gid)
        operation.run(['/usr/bin/unshare','--net','--','/usr/bin/setpriv','--reuid',str(user.pw_uid),'--regid',str(group.gr_gid),
                       '--clear-groups','--no-new-privs','--bounding-set=-all','--inh-caps=-all','--ambient-caps=-all',
                       str(PYTHON),'-I','-B',str(release/'engineering/tools/rras_history/production_entry.py'),'initialize-empty'],
                      'initialize-empty')
        dbpath=STORE/'history.sqlite3';info=dbpath.lstat()
        if info.st_uid!=user.pw_uid or stat.S_IMODE(info.st_mode)!=0o600 or info.st_nlink!=1:
            raise ValueError('new database custody differs')
        db=sqlite3.connect(dbpath.as_uri()+'?mode=ro',uri=True)
        try:
            if db.execute('PRAGMA integrity_check').fetchall()!=[('ok',)] or db.execute('PRAGMA user_version').fetchone()[0]!=1:
                raise ValueError('empty database integrity differs')
            for table in ('submissions','outbox'):
                if db.execute('SELECT count(*) FROM '+table).fetchone()[0]!=0:raise ValueError('nonempty initial database')
        finally:db.close()
        write_new(UNIT_FILE,files['deployment/rras-engineering-history.service'],0o644)
        write_new(WRAPPER,files['deployment/rras-history-client'],0o755)
        operation.run(['/usr/bin/systemctl','daemon-reload'],'load-inactive-unit')
        state=status()
        if state.get('ActiveState')!='inactive' or state.get('MainPID')!='0' or state.get('UnitFileState')!='disabled':
            raise ValueError('history unit must remain inactive and disabled')
        absent(RUNTIME)
        result={'phase':'history_inactive_install_complete','release':str(release),'journal':str(journal),
                'uid':user.pw_uid,'gid':group.gr_gid,'service_started':False,'service_enabled':False,
                'activation_authorized':False,'backup_verified':False,'backup_deferred_by_operator':True,'api_calls':0}
        write_new(journal/'complete.json',encoded(result));return result
    except Exception as error:
        write_new(journal/'failure-private.txt',traceback.format_exc().encode())
        raise ValueError('inactive installation stopped; preserve journal '+str(journal)) from error


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate',required=True);parser.add_argument('--manifest-sha256',required=True)
    parser.add_argument('--check-only',action='store_true');args=parser.parse_args()
    try:print(json.dumps(install(Path(args.candidate),args.manifest_sha256,check_only=args.check_only),indent=2))
    except Exception:
        sys.stderr.write('Inactive history installation refused/stopped. Preserve state; no automatic retry.\n');raise SystemExit(1)
