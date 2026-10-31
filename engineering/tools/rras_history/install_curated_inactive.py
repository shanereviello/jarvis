"""Stdlib-only additive inactive installation; no service start or publication.

Appended to the exact release verifier. Partial installs preserve evidence.
"""
import argparse
import grp
import pwd
import sys

RELEASES=Path('/opt/rras-engineering/releases')
STORE=Path('/var/lib/rras-curated-history')
PUBLICATIONS=Path('/var/lib/rras-curated-publications')
CONFIG=Path('/etc/rras-curated-history')
UNIT_FILE=Path('/etc/systemd/system/rras-curated-history-read.service')
UNIT=UNIT_FILE.name
WRAPPER=Path('/usr/local/sbin/rras-curated-publication')
JOURNALS=Path('/var/lib/rras-curated-installations')
RUNTIME=Path('/run/rras-curated-history')
ACCOUNT='rras-curated-reader'
PYTHON=Path('/opt/rras-engineering/releases/native-10/venv/bin/python')
ENV={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','LANG':'C.UTF-8'}


def protected(path):
    if path.resolve(strict=True)!=path:raise ValueError('canonical root path required')
    for item in (path,*path.parents):
        info=item.lstat()
        if item.is_symlink() or info.st_uid!=0 or info.st_mode&0o022:raise ValueError('protected root path required')


def absent(path):
    if path.exists() or path.is_symlink():raise ValueError('existing install state refused; preserve evidence')


def command(argv):return subprocess.run(argv,stdin=subprocess.DEVNULL,capture_output=True,env=ENV,timeout=30)


def status():
    result=command(['/usr/bin/systemctl','show',UNIT,'--property=LoadState,ActiveState,MainPID,UnitFileState'])
    if result.returncode:raise ValueError('unit state unavailable')
    return dict(line.split('=',1) for line in result.stdout.decode().splitlines() if '=' in line)


def accepted_runtime(files):
    # Tie installation to protected host evidence and identical runtime bytes.
    evidence=Path('/var/lib/rras-curated-container-acceptance-attempt04-20261030/complete.json')
    protected(evidence);record=decode(regular(evidence,256*1024))
    if (record.get('phase')!='isolated_curated_reader_container_verified' or len(record.get('cases',[]))!=9 or
            record.get('api_calls')!=0 or record.get('temporary_account_removed') is not True or
            record.get('fixture_unit_stopped') is not True or record.get('fixture_socket_removed') is not True or
            any(record.get(key) is not False for key in ('production_services_mutated','production_history_changed',
                'production_journal_changed','hermes_configuration_changed','real_credentials_used'))):raise ValueError('protected host acceptance differs')
    accepted=Path('/opt/rras-engineering/releases/history-curated-container-host-9bad384940b2')
    protected(accepted)
    raw=regular(accepted/MANIFEST,256*1024)
    if hashlib.sha256(raw).hexdigest()!='9bad384940b285e29da8573c502e34df41b548debff35f5ea3197dbad2864e37':raise ValueError('accepted release manifest differs')
    prior=decode(raw)
    for name,value in files.items():
        if name in DEPLOYMENT or name=='engineering/tools/rras_history/curated_install_package.py':continue
        path=accepted/name;protected(path)
        if prior['files'].get(name)!=hashlib.sha256(value).hexdigest() or regular(path)!=value:
            raise ValueError('runtime differs from actual host-accepted bytes')


def preflight(candidate,expected):
    if os.getuid()!=0 or os.geteuid()!=0:raise ValueError('explicit administrator installation required')
    manifest,files=verify(candidate,expected);accepted_runtime(files)
    release=Path(manifest['release']);journal=JOURNALS/expected
    owner=pwd.getpwnam('rras-history');group=grp.getgrnam('rras-history')
    if owner.pw_uid!=OWNER or owner.pw_gid!=OWNER or group.gr_gid!=OWNER or set(os.getgrouplist('rras-history',OWNER))!={OWNER}:
        raise ValueError('existing history owner identity differs')
    for lookup,value in ((pwd.getpwnam,ACCOUNT),(grp.getgrnam,ACCOUNT),(pwd.getpwuid,READER),(grp.getgrgid,READER)):
        try:lookup(value)
        except KeyError:continue
        raise ValueError('reader identity allocated; do not adopt')
    for path in Path('/proc').glob('[0-9]*/status'):
        try:lines=path.read_text().splitlines()
        except (FileNotFoundError,ProcessLookupError):continue
        if any(line.startswith(('Uid:','Gid:')) and str(READER) in line.split()[1:] for line in lines):raise ValueError('reader numeric identity active')
    for path in (RELEASES,STORE.parent,PUBLICATIONS.parent,CONFIG.parent,UNIT_FILE.parent,WRAPPER.parent,JOURNALS.parent,
                 PYTHON.parent,PYTHON.resolve(strict=True),Path('/usr/bin/systemctl'),Path('/usr/sbin/useradd'),
                 Path('/usr/sbin/groupadd'),Path('/usr/bin/env'),Path('/bin/sh').resolve(strict=True)):protected(path)
    for path in (release,STORE,PUBLICATIONS,CONFIG,UNIT_FILE,WRAPPER,RUNTIME):absent(path)
    if JOURNALS.exists():
        protected(JOURNALS)
        if not JOURNALS.is_dir() or stat.S_IMODE(JOURNALS.stat().st_mode)!=0o700:raise ValueError('private installation journal required')
    elif JOURNALS.is_symlink():raise ValueError('journal symlink refused')
    absent(journal)
    current=status()
    if current.get('LoadState')!='not-found' or current.get('ActiveState')!='inactive' or current.get('MainPID')!='0':raise ValueError('existing reader unit refused')
    return manifest,files,release,journal


def sync(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


def mkdir(path,mode=0o700,uid=0,gid=0):
    path.mkdir(mode=mode);os.chown(path,uid,gid);os.chmod(path,mode);sync(path.parent)


def write(path,raw,mode=0o600,uid=0,gid=0):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
    with os.fdopen(fd,'wb') as stream:
        os.fchmod(stream.fileno(),mode);os.fchown(stream.fileno(),uid,gid)
        stream.write(raw);stream.flush();os.fsync(stream.fileno())
    sync(path.parent)


def install(candidate,expected,*,check_only=False,approve_installation=False):
    if not check_only and approve_installation is not True:raise ValueError('explicit inactive installation approval required')
    manifest,files,release,journal=preflight(candidate,expected)
    if check_only:return {'phase':'inactive_curated_preflight_passed','mutations':False,'activation_authorized':False}
    os.umask(0o077)
    if not JOURNALS.exists():mkdir(JOURNALS)
    mkdir(journal);write(journal/'intent.json',encoded({'manifest_sha256':expected,'release':str(release),'activation_authorized':False}))
    count=[0]
    def checked(argv,tag):
        count[0]+=1;write(journal/f'{count[0]:02d}-{tag}-intent.json',encoded({'argv':argv}))
        result=command(argv)
        write(journal/f'{count[0]:02d}-{tag}-stdout',result.stdout);write(journal/f'{count[0]:02d}-{tag}-stderr',result.stderr)
        if result.returncode:raise ValueError('inactive install command failed; preserve diagnostics')
    try:
        checked(['/usr/sbin/groupadd','--gid',str(READER),ACCOUNT],'group-create')
        checked(['/usr/sbin/useradd','--system','--uid',str(READER),'--gid',ACCOUNT,'--no-user-group',
                 '--no-create-home','--home-dir','/nonexistent','--shell','/usr/sbin/nologin','--no-log-init','--password','!',ACCOUNT],'reader-create')
        user=pwd.getpwnam(ACCOUNT);group=grp.getgrnam(ACCOUNT)
        if (user.pw_uid!=READER or user.pw_gid!=READER or group.gr_gid!=READER or group.gr_mem or
                user.pw_dir!='/nonexistent' or user.pw_shell!='/usr/sbin/nologin' or set(os.getgrouplist(ACCOUNT,READER))!={READER}):
            raise ValueError('installed reader identity differs')
        mkdir(release,0o755)
        for name,raw in sorted(files.items()):
            path=release/name
            for parent in reversed(path.relative_to(release).parents):
                if parent==Path('.'):continue
                directory=release/parent
                if not directory.exists():mkdir(directory,0o755)
            write(path,raw,0o444)
        write(release/MANIFEST,encoded(manifest),0o444);verify(release,expected)
        mkdir(STORE,0o755);mkdir(STORE/'catalog',0o700,OWNER,OWNER);mkdir(STORE/'catalog/generations',0o700,OWNER,OWNER)
        write(STORE/'catalog/configuration.json',encoded({'contract':'engineering-curated-catalog.v1','owner_uid':OWNER,'repositories':['jarvis']}),0o600,OWNER,OWNER)
        mkdir(PUBLICATIONS);mkdir(PUBLICATIONS/'requests');mkdir(PUBLICATIONS/'attempts')
        mkdir(CONFIG,0o750,0,OWNER);write(CONFIG/'read-policy.json',files['deployment/read-policy.json'],0o640,0,OWNER)
        write(UNIT_FILE,files['deployment/rras-curated-history-read.service'],0o644)
        write(WRAPPER,files['deployment/rras-curated-publication'],0o755)
        checked(['/usr/bin/systemctl','daemon-reload'],'load-inactive-unit')
        current=status()
        if current.get('ActiveState')!='inactive' or current.get('MainPID')!='0' or current.get('UnitFileState')!='disabled':raise ValueError('reader must remain inactive and disabled')
        absent(RUNTIME);absent(STORE/'catalog/current.json')
        result={'phase':'inactive_curated_install_complete','release':str(release),'manifest_sha256':expected,'journal':str(journal),
            'reader_uid':READER,'catalog_empty':True,'service_started':False,'service_enabled':False,'activation_authorized':False,
            'hermes_configuration_changed':False,'history_records_added':0,'api_calls':0,'backup_verified':False,
            'backup_deferred_by_operator':True,'automatic_retry':False}
        write(journal/'complete.json',encoded(result));return result
    except Exception as error:
        write(journal/'stopped.json',encoded({'exception_type':type(error).__name__,'automatic_retry':False,'automatic_rollback':False}))
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate',required=True);parser.add_argument('--manifest-sha256',required=True)
    parser.add_argument('--check-only',action='store_true');parser.add_argument('--approve-inactive-installation',action='store_true')
    args=parser.parse_args()
    try:print(json.dumps(install(Path(args.candidate),args.manifest_sha256,check_only=args.check_only,approve_installation=args.approve_inactive_installation),indent=2))
    except Exception:raise SystemExit('Inactive curated installation stopped; preserve evidence. No automatic retry.')
