"""Stdlib root bootstrap appended to host_package verifier; synthetic fixture only."""
import argparse
import sys


def protected(path):
    for item in (path,*path.parents):
        info=item.lstat()
        if item.is_symlink() or info.st_uid!=0 or info.st_mode&0o022:raise ValueError('protected fixture destination required')


def stage(candidate,expected):
    if os.getuid()!=0 or os.geteuid()!=0:raise ValueError('explicit sudo acceptance required')
    release=Path('/opt/rras-engineering/releases/history-web-host-'+expected[:12])
    protected(release.parent);protected(STATE.parent);protected(RUNTIME.parent)
    protected(PYTHON)
    for path in (release,STATE,RUNTIME):
        if path.exists() or path.is_symlink():raise ValueError('preserve existing fixture; no automatic retry')
    manifest,files=verify(candidate,expected)
    os.umask(0o022);release.mkdir(mode=0o755)
    for name,raw in files.items():
        path=release/name;path.parent.mkdir(mode=0o755,parents=True,exist_ok=True)
        with path.open('xb') as stream:
            os.fchmod(stream.fileno(),0o444);stream.write(raw);stream.flush();os.fsync(stream.fileno())
    with (release/MANIFEST).open('xb') as stream:os.fchmod(stream.fileno(),0o444);stream.write(encoded(manifest));stream.flush();os.fsync(stream.fileno())
    for directory in sorted([release,*[p for p in release.rglob('*') if p.is_dir()]],key=lambda p:len(p.parts),reverse=True):
        fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
    result=subprocess.run([str(PYTHON),'-I','-B',str(release/'engineering/tools/rras_history_web/host_driver.py')],
        stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=300,
        env={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','LANG':'C.UTF-8'})
    if result.returncode:
        for line in result.stderr.splitlines():
            try:value=decode(line)
            except (ValueError,UnicodeError):continue
            if type(value) is dict and value.get('phase')=='dashboard_host_acceptance_stopped':print(json.dumps(value),file=sys.stderr)
        raise ValueError('fixture stopped; preserve evidence')
    value=decode(result.stdout)
    if value.get('phase')!='isolated_dashboard_host_verified' or value.get('api_calls')!=0 or value.get('fixture_source_database_unchanged') is not True:raise ValueError('fixture result differs')
    value.update(acceptance_release=str(release),manifest_sha256=expected,source_commit=manifest['source_commit'])
    return value


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--candidate',required=True);parser.add_argument('--manifest-sha256',required=True);args=parser.parse_args()
    try:print(json.dumps(stage(Path(args.candidate),args.manifest_sha256),indent=2))
    except Exception:
        sys.stderr.write('Dashboard host acceptance stopped; preserve protected evidence. No automatic retry.\n');raise SystemExit(1)
