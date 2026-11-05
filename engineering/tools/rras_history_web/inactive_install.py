"""Appended to the production verifier. Additive inactive install; never activate."""
import argparse
import grp
import pwd
import sys
import traceback

ACCOUNT='rras-history-web'
UID=993
CONFIG=Path('/etc/rras-engineering-history-web')
UNIT='rras-engineering-history-web.service'
UNIT_FILE=Path('/etc/systemd/system')/UNIT
JOURNALS=Path('/var/lib/rras-history-web-installations')
HISTORY_UNIT='rras-engineering-history.service'
POLICY=Path('/etc/rras-engineering-history/access-policy.json')
ENV={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','LANG':'C.UTF-8'}


def protected(path):
    for item in (path,*path.parents):
        info=item.lstat()
        if item.is_symlink() or info.st_uid!=0 or info.st_mode&0o022:raise ValueError('protected path required')


def absent(path):
    if path.exists() or path.is_symlink():raise ValueError('existing install state; preserve evidence')


def command(argv):return subprocess.run(argv,stdin=subprocess.DEVNULL,capture_output=True,timeout=30,env=ENV,cwd='/')


def status(unit):
    result=command(['/usr/bin/systemctl','show',unit,'--property=LoadState,ActiveState,MainPID,UnitFileState'])
    if result.returncode:raise ValueError('unit status unavailable')
    return dict(line.split('=',1) for line in result.stdout.decode().splitlines() if '=' in line)


def configuration(raw,expected):
    if type(expected) is not str or not re.fullmatch('[0-9a-f]{64}',expected) or hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('configuration digest changed')
    value=decode(raw)
    fields={'contract','uid','gid','history_uid','history_socket','repositories','issuer','audience','email','origin','bind','port'}
    if type(value) is not dict or set(value)!=fields:raise ValueError('exact configuration fields required')
    if (value['contract']!='engineering-history-web.v1' or type(value['uid']) is not int or value['uid']!=UID or
            type(value['gid']) is not int or value['gid']!=UID or type(value['history_uid']) is not int or value['history_uid']!=995 or
            value['history_socket']!='/run/rras-engineering-history/service.sock' or value['repositories']!=['jarvis'] or
            value['bind']!='172.19.0.1' or type(value['port']) is not int or value['port']!=18764 or
            any(type(value[field]) is not str for field in ('issuer','audience','email','origin'))):raise ValueError('reviewed inactive identity/scope differs')
    # Full application validation executes only as the new unprivileged identity
    # after immutable staging, never from a caller-writable import as root.
    return value


def user_command():
    return ['/usr/sbin/useradd','--system','--uid',str(UID),'--gid',ACCOUNT,'--no-user-group','--no-create-home',
        '--home-dir','/nonexistent','--shell','/usr/sbin/nologin','--no-log-init','--password','!',ACCOUNT]


def verify_identity():
    user=pwd.getpwnam(ACCOUNT);group=grp.getgrnam(ACCOUNT)
    if any(item.pw_gid==UID and item.pw_name!=ACCOUNT for item in pwd.getpwall()):raise ValueError('unrelated primary group member')
    if (user.pw_uid!=UID or user.pw_gid!=UID or group.gr_gid!=UID or group.gr_mem or user.pw_dir!='/nonexistent' or
            user.pw_shell!='/usr/sbin/nologin' or pwd.getpwuid(UID).pw_name!=ACCOUNT or set(os.getgrouplist(ACCOUNT,UID))!={UID}):raise ValueError('dedicated identity differs')


def preflight(candidate,expected,config_path,config_sha):
    if os.getuid()!=0 or os.geteuid()!=0:raise ValueError('explicit administrator invocation required')
    manifest,files=verify(candidate,expected);raw=regular(config_path,16384);configuration(raw,config_sha)
    release=Path(manifest['release']);journal=JOURNALS/release.name
    for path in (release.parent,CONFIG.parent,UNIT_FILE.parent,JOURNALS.parent,Path(PYTHON)):protected(path)
    for tool in ('/usr/bin/systemctl','/usr/bin/setpriv','/usr/sbin/useradd','/usr/sbin/groupadd'):protected(Path(tool).resolve(strict=True))
    if JOURNALS.exists() or JOURNALS.is_symlink():protected(JOURNALS)
    for path in (release,CONFIG,UNIT_FILE,journal):absent(path)
    state=status(UNIT)
    if state.get('LoadState')!='not-found' or state.get('MainPID')!='0' or state.get('ActiveState')!='inactive':raise ValueError('dashboard unit already exists')
    for lookup,key in ((pwd.getpwnam,ACCOUNT),(pwd.getpwuid,UID),(grp.getgrnam,ACCOUNT),(grp.getgrgid,UID)):
        try:lookup(key)
        except KeyError:continue
        raise ValueError('dedicated identity occupied; do not adopt')
    if any(ACCOUNT in group.gr_mem for group in grp.getgrall()) or any(user.pw_gid==UID for user in pwd.getpwall()):raise ValueError('existing named or primary group association')
    for path in Path('/proc').glob('[0-9]*/status'):
        try:lines=path.read_text().splitlines()
        except (FileNotFoundError,ProcessLookupError):continue
        if any(line.startswith(('Uid:','Gid:')) and str(UID) in line.split()[1:] for line in lines):raise ValueError('dedicated identity active')
    history=status(HISTORY_UNIT)
    if history.get('ActiveState')!='active' or int(history.get('MainPID','0'))<1:raise ValueError('history service baseline unavailable')
    policy_sha=hashlib.sha256(regular(POLICY,128*1024)).hexdigest()
    return manifest,files,raw,journal,history['MainPID'],policy_sha


def sync_directory(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


def write_new(path,raw,mode=0o600,gid=0):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
    with os.fdopen(fd,'wb') as stream:os.fchmod(stream.fileno(),mode);os.fchown(stream.fileno(),0,gid);stream.write(raw);stream.flush();os.fsync(stream.fileno())
    fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


class Install:
    def __init__(self,journal):self.journal=journal;self.step=0
    def run(self,argv,tag):
        self.step+=1;prefix=f'{self.step:02d}-{tag}'
        write_new(self.journal/(prefix+'-intent.json'),encoded({'argv':argv}))
        result=command(argv)
        write_new(self.journal/(prefix+'-stdout'),result.stdout);write_new(self.journal/(prefix+'-stderr'),result.stderr)
        if result.returncode:raise ValueError('inactive installation command refused; preserve diagnostics')
        return result


def install(candidate,expected,config_path,config_sha,check_only=False):
    manifest,files,raw,journal,history_pid,policy_sha=preflight(candidate,expected,config_path,config_sha)
    if check_only:return dict(phase='inactive_dashboard_install_preflight_passed',release=manifest['release'],config_sha256=config_sha,
        mutations=False,installation_authorized=False,activation_authorized=False)
    os.umask(0o077)
    if not JOURNALS.exists():JOURNALS.mkdir(mode=0o700);sync_directory(JOURNALS.parent)
    journal.mkdir(mode=0o700);sync_directory(JOURNALS);engine=Install(journal)
    write_new(journal/'intent.json',encoded(dict(release=manifest['release'],manifest_sha256=expected,config_sha256=config_sha,
        history_pid=history_pid,history_policy_sha256=policy_sha,service_start_authorized=False,history_grant_authorized=False)))
    try:
        engine.run(['/usr/sbin/groupadd','--gid',str(UID),ACCOUNT],'create-group')
        engine.run(user_command(),'create-user');verify_identity()
        release=Path(manifest['release']);os.umask(0o022);release.mkdir(mode=0o755)
        for name,content in files.items():
            path=release/name;path.parent.mkdir(mode=0o755,parents=True,exist_ok=True);write_new(path,content,mode=0o444)
        write_new(release/MANIFEST,encoded(manifest),mode=0o444)
        for directory in sorted([release,*[p for p in release.rglob('*') if p.is_dir()]],key=lambda p:len(p.parts),reverse=True):
            fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY)
            try:os.fsync(fd)
            finally:os.close(fd)
        sync_directory(release.parent)
        CONFIG.mkdir(mode=0o750);os.chown(CONFIG,0,UID);os.chmod(CONFIG,0o750);sync_directory(CONFIG.parent)
        write_new(CONFIG/'config.json',raw,mode=0o640,gid=UID)
        # Parse exact installed configuration and identity under UID993 with
        # no extra groups/caps/network request or service dispatch.
        probe="""import importlib.util,sys,json,hashlib,os
from pathlib import Path
root=Path(sys.argv[1]);sys.path.insert(0,str(root/'vendor'))
s=importlib.util.spec_from_file_location('installed_web_entry',root/'engineering/tools/rras_history_web/entry.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
v=m.protected_configuration('/etc/rras-engineering-history-web/config.json');m.identity(v)
print(json.dumps(dict(installed_configuration_verified=True,uid=os.getuid(),configuration_sha256=hashlib.sha256(Path('/etc/rras-engineering-history-web/config.json').read_bytes()).hexdigest(),history_contacted=False,listener_started=False)))
"""
        result=engine.run(['/usr/bin/setpriv','--reuid',str(UID),'--regid',str(UID),'--clear-groups','--no-new-privs',
            '--bounding-set=-all','--inh-caps=-all','--ambient-caps=-all',PYTHON,'-I','-S','-B','-c',probe,str(release)],'verify-installed-config')
        checked=decode(result.stdout)
        if checked.get('installed_configuration_verified') is not True or checked.get('configuration_sha256')!=config_sha:raise ValueError('installed config probe differs')
        verify(release,expected)
        write_new(UNIT_FILE,files['deployment/rras-engineering-history-web.service'],mode=0o644)
        engine.run(['/usr/bin/systemctl','daemon-reload'],'reload-unit-definitions')
        after=status(UNIT)
        if after.get('LoadState')!='loaded' or after.get('ActiveState')!='inactive' or after.get('MainPID')!='0' or after.get('UnitFileState')!='disabled':raise ValueError('new dashboard unit not disabled/inactive')
        if status(HISTORY_UNIT).get('MainPID')!=history_pid or hashlib.sha256(regular(POLICY,128*1024)).hexdigest()!=policy_sha:raise ValueError('history baseline changed; preserve evidence')
        value=dict(phase='inactive_dashboard_install_complete',release=str(release),journal=str(journal),manifest_sha256=expected,
            config_sha256=config_sha,uid=UID,gid=UID,service_started=False,service_enabled=False,history_grant_changed=False,
            history_service_restarted=False,cloudflare_changed=False,activation_authorized=False,model_api_calls=0,
            backup_verified=False,backup_deferred_by_operator=True,automatic_retry=False)
        write_new(journal/'complete.json',encoded(value));return value
    except Exception:
        write_new(journal/'failure-private.txt',traceback.format_exc().encode());raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('operation',choices=('preflight','install'))
    parser.add_argument('--candidate',required=True);parser.add_argument('--manifest-sha256',required=True)
    parser.add_argument('--config',required=True);parser.add_argument('--config-sha256',required=True);args=parser.parse_args()
    try:print(json.dumps(install(Path(args.candidate),args.manifest_sha256,Path(args.config),args.config_sha256,check_only=args.operation=='preflight'),indent=2))
    except Exception as error:
        print(json.dumps(dict(phase='inactive_dashboard_install_stopped',exception_type=type(error).__name__,
            frames=[dict(file=Path(frame.filename).name,line=frame.lineno,function=frame.name) for frame in traceback.extract_tb(error.__traceback__)],
            protected_evidence=str(JOURNALS),automatic_retry=False)),file=sys.stderr);raise SystemExit(1)
