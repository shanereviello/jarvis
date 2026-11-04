"""Appended to production verifier with an embedded reviewed probe; no install."""
import argparse
import grp
import pwd
import sys

STATE=Path('/var/lib/rras-history-web-package-check-attempt02-20261104')


def protected(path):
    for item in (path,*path.parents):
        info=item.lstat()
        if item.is_symlink() or info.st_uid!=0 or info.st_mode&0o022:raise ValueError('protected check destination required')


def check(candidate,expected):
    if os.getuid()!=0 or os.geteuid()!=0:raise ValueError('explicit sudo package check required')
    release=Path('/opt/rras-engineering/releases/history-web-package-check-attempt02-'+expected[:12])
    protected(release.parent);protected(STATE.parent);protected(Path(PYTHON))
    for path in (release,STATE):
        if path.exists() or path.is_symlink():raise ValueError('preserve existing check; no automatic retry')
    for lookup in (pwd.getpwuid,grp.getgrgid):
        try:lookup(61165)
        except KeyError:pass
        else:raise ValueError('probe numeric identity occupied')
    for path in Path('/proc').glob('[0-9]*/status'):
        try:lines=path.read_text().splitlines()
        except (FileNotFoundError,ProcessLookupError):continue
        if any(line.startswith(('Uid:','Gid:')) and '61165' in line.split()[1:] for line in lines):raise ValueError('probe identity active')
    manifest,files=verify(candidate,expected)
    os.umask(0o077);STATE.mkdir(mode=0o700)
    os.umask(0o022);release.mkdir(mode=0o755)
    for name,raw in files.items():
        path=release/name;path.parent.mkdir(mode=0o755,parents=True,exist_ok=True)
        with path.open('xb') as stream:os.fchmod(stream.fileno(),0o444);stream.write(raw);stream.flush();os.fsync(stream.fileno())
    with (release/MANIFEST).open('xb') as stream:os.fchmod(stream.fileno(),0o444);stream.write(encoded(manifest));stream.flush();os.fsync(stream.fileno())
    tools=release/'acceptance-tools';tools.mkdir(mode=0o755)
    with (tools/'probe.py').open('xb') as stream:os.fchmod(stream.fileno(),0o444);stream.write(PROBE_BYTES);stream.flush();os.fsync(stream.fileno())
    for directory in sorted([release,*[p for p in release.rglob('*') if p.is_dir()]],key=lambda p:len(p.parts),reverse=True):
        fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
    verify(release,expected)
    result=subprocess.run(['/usr/bin/unshare','--net','--','/usr/bin/setpriv','--reuid','61165','--regid','61165',
        '--clear-groups','--no-new-privs','--bounding-set=-all','--inh-caps=-all','--ambient-caps=-all',PYTHON,'-I','-S','-B',
        str(tools/'probe.py'),str(release),str(STATE),os.readlink('/proc/self/ns/net')],stdin=subprocess.DEVNULL,capture_output=True,timeout=60,cwd='/',
        env={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','LANG':'C.UTF-8'})
    for name,raw in (('probe-stdout.json',result.stdout),('probe-stderr.txt',result.stderr)):
        with (STATE/name).open('xb') as stream:os.fchmod(stream.fileno(),0o600);stream.write(raw)
    if result.returncode:
        frames=[dict(file=Path(file).name,line=int(line),function=function.strip()) for file,line,function in re.findall(r'File "([^"]+)", line ([0-9]+), in ([^\n]+)',result.stderr[:16384].decode('utf-8',errors='replace'))]
        print(json.dumps(dict(phase='protected_package_probe_stopped',returncode=result.returncode,frames=frames,protected_evidence=str(STATE),automatic_retry=False)),file=sys.stderr)
        raise ValueError('protected probe stopped; preserve evidence')
    value=decode(result.stdout)
    if value.get('phase')!='protected_dashboard_package_probe_verified' or value.get('api_calls')!=0:raise ValueError('unexpected probe result')
    verify(release,expected)
    value.update(phase='protected_dashboard_package_host_verified',acceptance_copy=str(release),journal=str(STATE),
        manifest_sha256=expected,source_commit=manifest['source_commit'],probe_sha256=hashlib.sha256(PROBE_BYTES).hexdigest(),
        production_release_installed=False,production_services_mutated=False,production_history_changed=False,
        production_grant_changed=False,cloudflare_changed=False,accounts_created=False,automatic_retry=False)
    with (STATE/'result.json').open('xb') as stream:os.fchmod(stream.fileno(),0o600);stream.write(encoded(value))
    return value


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--candidate',required=True);parser.add_argument('--manifest-sha256',required=True);args=parser.parse_args()
    try:print(json.dumps(check(Path(args.candidate),args.manifest_sha256),indent=2))
    except Exception:
        sys.stderr.write('Protected dashboard package check stopped; preserve evidence. No automatic retry.\n');raise SystemExit(1)
