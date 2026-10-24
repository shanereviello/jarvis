"""First activation only; separate live approval, no retry/rollback or data writes.

Generated after the approved stdlib verifier and inactive-install primitives.
"""
import time


def private_root_file(path):
    protected(path)
    info=path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or stat.S_IMODE(info.st_mode)!=0o600:
        raise ValueError('private root journal file required')
    return regular(path,256*1024)


def empty_database(uid,gid):
    protected(STORE.parent)
    info=STORE.lstat()
    if not stat.S_ISDIR(info.st_mode) or STORE.is_symlink() or info.st_uid!=uid or info.st_gid!=gid or stat.S_IMODE(info.st_mode)!=0o700:
        raise ValueError('installed database directory custody differs')
    path=STORE/'history.sqlite3';info=path.lstat()
    if path.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_uid!=uid or info.st_gid!=gid or stat.S_IMODE(info.st_mode)!=0o600:
        raise ValueError('installed database custody differs')
    db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=5)
    try:
        if db.execute('PRAGMA integrity_check').fetchall()!=[('ok',)] or db.execute('PRAGMA user_version').fetchone()[0]!=1:
            raise ValueError('installed database integrity differs')
        for table in ('submissions','outbox'):
            if db.execute('SELECT count(*) FROM '+table).fetchone()[0]:raise ValueError('first activation requires empty database')
    finally:db.close()


def activation_preflight(release,expected):
    if os.getuid()!=0 or os.geteuid()!=0:raise ValueError('explicit administrator invocation required')
    protected(release)
    manifest,files=verify(release,expected)
    if Path(manifest['release'])!=release:raise ValueError('installed release differs')
    for name in files:
        path=release/name;protected(path)
        if stat.S_IMODE(path.stat().st_mode)!=0o444:raise ValueError('installed release mode differs')
    user=pwd.getpwnam(ACCOUNT);group=grp.getgrnam(ACCOUNT)
    if (user.pw_uid in (0,996,997,1000) or user.pw_uid<1 or user.pw_gid!=group.gr_gid or group.gr_mem or
            user.pw_dir!='/nonexistent' or user.pw_shell!='/usr/sbin/nologin' or
            any(p.pw_gid==group.gr_gid and p.pw_name!=ACCOUNT for p in pwd.getpwall())):
        raise ValueError('installed identity differs')
    journal=JOURNALS/release.name
    complete=decode(private_root_file(journal/'complete.json'))
    if (complete.get('phase')!='history_inactive_install_complete' or complete.get('uid')!=user.pw_uid or
            complete.get('gid')!=group.gr_gid or complete.get('release')!=str(release) or
            complete.get('service_started') is not False or complete.get('service_enabled') is not False or
            complete.get('backup_deferred_by_operator') is not True):
        raise ValueError('inactive installation receipt differs')
    for path,name,mode in ((UNIT_FILE,'deployment/rras-engineering-history.service',0o644),
                          (WRAPPER,'deployment/rras-history-client',0o755),
                          (CONFIG/'access-policy.json','deployment/access-policy.json',0o640)):
        protected(path)
        if regular(path)!=files[name] or stat.S_IMODE(path.stat().st_mode)!=mode:raise ValueError('installed artifact differs')
    if (CONFIG.stat().st_gid!=group.gr_gid or stat.S_IMODE(CONFIG.stat().st_mode)!=0o750 or
            (CONFIG/'access-policy.json').stat().st_gid!=group.gr_gid):raise ValueError('policy custody differs')
    protected(PYTHON.parent);protected(PYTHON.resolve(strict=True))
    for executable in ('/usr/bin/systemctl','/usr/bin/setpriv','/usr/bin/unshare','/usr/bin/setfacl','/usr/bin/getfacl'):
        protected(Path(executable))
    state=status()
    if state.get('LoadState')!='loaded' or state.get('ActiveState')!='inactive' or state.get('MainPID')!='0' or state.get('UnitFileState')!='disabled':
        raise ValueError('first activation requires stopped disabled unit')
    activation=journal/'activation-01';absent(activation);absent(RUNTIME)
    empty_database(user.pw_uid,group.gr_gid)
    return user.pw_uid,group.gr_gid,activation


def probe_command(release,uid,service_uid,role):
    if (uid,role) not in ((1000,'reader'),(996,'worker-denial'),(997,'worker-denial')):
        raise ValueError('unknown activation probe identity')
    return ['/usr/bin/unshare','--net','--','/usr/bin/setpriv','--reuid',str(uid),'--regid',str(uid),
            '--clear-groups','--no-new-privs','--bounding-set=-all','--inh-caps=-all','--ambient-caps=-all',
            str(PYTHON),'-I','-B','-c',ACTIVATION_PROBE,str(release),str(service_uid),role]


def service_boundary(uid,gid):
    state=status()
    if state.get('ActiveState')!='active':raise ValueError('history service not active')
    pid=int(state['MainPID'])
    if pid<1:raise ValueError('history service PID absent')
    fields=dict(line.split(':',1) for line in Path(f'/proc/{pid}/status').read_text().splitlines() if ':' in line)
    if set(map(int,fields['Uid'].split()))!={uid} or set(map(int,fields['Gid'].split()))!={gid}:
        raise ValueError('live service identity differs')
    if not set(map(int,fields['Groups'].split())) <= {gid} or fields['NoNewPrivs'].strip()!='1':
        raise ValueError('live service privilege boundary differs')
    if any(int(fields[name].strip(),16) for name in ('CapEff','CapPrm','CapInh','CapBnd','CapAmb')):
        raise ValueError('live service has capabilities')
    if os.readlink(f'/proc/{pid}/ns/net')==os.readlink('/proc/self/ns/net'):
        raise ValueError('history service network isolation differs')
    return pid


def activate(release,expected,*,check_only=False):
    uid,gid,journal=activation_preflight(release,expected)
    if check_only:return {'phase':'history_activation_preflight_passed','mutations':False,'activation_authorized':False}
    os.umask(0o077);mkdir_new(journal)
    operation=Install(journal)
    write_new(journal/'intent.json',encoded({'release':str(release),'manifest_sha256':expected,
               'scope':'start-history-verify-read-only-then-enable-at-boot','automatic_retry':False,'backup_verified':False}))
    try:
        operation.run(['/usr/bin/systemctl','start',UNIT],'start-history')
        # Bounded wait for socket only; no automatic start/execution retry.
        deadline=time.monotonic()+10
        while not (RUNTIME/'service.sock').exists():
            if time.monotonic()>deadline:raise ValueError('history socket readiness deadline')
            time.sleep(0.1)
        pid=service_boundary(uid,gid)
        for caller,role in ((1000,'reader'),(996,'worker-denial'),(997,'worker-denial')):
            result=operation.run(probe_command(release,caller,uid,role),'probe-'+str(caller))
            value=json.loads(result.stdout)
            if value.get('uid')!=caller or value.get('private_files_denied') is not True:
                raise ValueError('activation probe result differs')
        empty_database(uid,gid)
        operation.run(['/usr/bin/systemctl','enable',UNIT],'enable-history-at-boot')
        state=status()
        if state.get('UnitFileState')!='enabled' or service_boundary(uid,gid)!=pid:
            raise ValueError('enabled live history state differs')
        result={'phase':'history_first_activation_complete','release':str(release),'journal':str(journal),
                'uid':uid,'gid':gid,'service_running':True,'enabled_at_boot':True,
                'read_only_client_acceptance':True,'production_records_added':0,'automatic_session_capture':False,
                'api_calls':0,'backup_verified':False,'backup_deferred_by_operator':True}
        write_new(journal/'complete.json',encoded(result));return result
    except Exception as error:
        write_new(journal/'failure-private.txt',traceback.format_exc().encode())
        raise ValueError('activation stopped; preserve live state and private journal') from error


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release',required=True);parser.add_argument('--manifest-sha256',required=True)
    parser.add_argument('--check-only',action='store_true');args=parser.parse_args()
    try:print(json.dumps(activate(Path(args.release),args.manifest_sha256,check_only=args.check_only),indent=2))
    except Exception:
        sys.stderr.write('History activation refused/stopped. Preserve state; no automatic retry or rollback.\n');raise SystemExit(1)
