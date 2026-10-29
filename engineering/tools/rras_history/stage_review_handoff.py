"""Stdlib bootstrap appended to the exact managed-host verifier."""
import argparse
import os
import subprocess
import sys


def protected(path):
    for item in (path,*path.parents):
        info=item.lstat()
        if item.is_symlink() or info.st_uid!=0 or info.st_mode&0o022:raise ValueError('protected fixture destination required')


def stage(candidate,expected):
    if os.getuid()!=0 or os.geteuid()!=0:raise ValueError('explicit sudo acceptance required')
    release=Path('/opt/rras-engineering/releases/history-review-handoff-host-'+expected[:12])
    protected(release.parent);protected(STATE.parent)
    native=Path('/opt/rras-engineering/releases/native-10/venv/bin/python')
    protected(native.parent);protected(native.resolve(strict=True))
    for path in (release,STATE):
        if path.exists() or path.is_symlink():raise ValueError('preserve existing fixture; no automatic retry')
    manifest,files=verify(candidate,expected);os.umask(0o022);release.mkdir(mode=0o755)
    for name,raw in files.items():
        path=release/name;path.parent.mkdir(mode=0o755,parents=True,exist_ok=True)
        with path.open('xb') as stream:
            os.fchmod(stream.fileno(),0o444);stream.write(raw);stream.flush();os.fsync(stream.fileno())
    with (release/MANIFEST).open('xb') as stream:
        os.fchmod(stream.fileno(),0o444);stream.write(encoded(manifest));stream.flush();os.fsync(stream.fileno())
    for directory in sorted([release,*[p for p in release.rglob('*') if p.is_dir()]],key=lambda p:len(p.parts),reverse=True):
        fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
    process=subprocess.Popen([str(native),'-I','-B',str(release/'engineering/tools/rras_history/review_handoff_driver.py')],
                             stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                             env={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','LANG':'C.UTF-8'})
    try:out,err=process.communicate(timeout=240)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:process.communicate(timeout=30)
        except subprocess.TimeoutExpired:process.kill();process.communicate(timeout=5)
        raise ValueError('managed host fixture deadline; preserve evidence')
    if process.returncode:
        for line in err.splitlines():
            try:record=decode(line)
            except (ValueError,UnicodeError):continue
            if type(record) is dict and record.get('phase')=='review_handoff_host_stopped':print(json.dumps(record),file=sys.stderr)
        raise ValueError('managed host fixture stopped; preserve evidence')
    result=decode(out)
    if result.get('phase')!='isolated_review_document_handoff_verified' or result.get('api_calls')!=0:raise ValueError('fixture result differs')
    result.update(acceptance_release=str(release),manifest_sha256=expected,source_commit=manifest['source_commit'])
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate',required=True);parser.add_argument('--manifest-sha256',required=True);args=parser.parse_args()
    try:print(json.dumps(stage(Path(args.candidate),args.manifest_sha256),indent=2))
    except Exception:
        sys.stderr.write('Review document handoff acceptance stopped; preserve protected evidence. No automatic retry.\n');raise SystemExit(1)
