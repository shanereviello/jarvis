"""Stdlib-only bootstrap appended to the pinned unit fixture verifier."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def protected(path):
    for item in (path,*path.parents):
        info=item.lstat()
        if item.is_symlink() or info.st_uid!=0 or info.st_mode&0o022:raise ValueError('protected unit fixture destination required')


def stage(candidate,expected):
    if os.getuid()!=0 or os.geteuid()!=0:raise ValueError('reviewed sudo invocation required')
    state=Path('/var/lib/rras-history-unit-acceptance-20261022')
    release=Path('/opt/rras-engineering/releases/history-unit-acceptance-'+expected[:12])
    protected(release.parent);protected(state.parent)
    if release.exists() or release.is_symlink() or state.exists() or state.is_symlink():
        raise ValueError('preserve existing unit fixture; no retry')
    manifest,files=verify(candidate,expected)
    os.umask(0o022);release.mkdir(mode=0o755)
    for name,raw in files.items():
        path=release/name;path.parent.mkdir(mode=0o755,parents=True,exist_ok=True)
        with path.open('xb') as stream:
            os.fchmod(stream.fileno(),0o444);stream.write(raw);stream.flush();os.fsync(stream.fileno())
    with (release/'unit-acceptance-manifest.json').open('xb') as stream:
        os.fchmod(stream.fileno(),0o444);stream.write(encoded(manifest));stream.flush();os.fsync(stream.fileno())
    for path in sorted({release,*[p.parent for p in release.rglob('*')]},key=lambda p:len(p.parts),reverse=True):
        os.chmod(path,0o755);fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
    process=subprocess.Popen(['/usr/bin/python3','-I','-B',str(release/'engineering/tools/rras_history/unit_acceptance.py')],
                             stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                             env={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','LANG':'C.UTF-8'})
    try:out,err=process.communicate(timeout=300)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:out,err=process.communicate(timeout=60)
        except subprocess.TimeoutExpired:process.kill();out,err=process.communicate(timeout=5)
        raise ValueError('unit acceptance timeout; preserve evidence')
    if process.returncode:
        # Orchestrator emits only typed frame metadata, never raw unit journals.
        for line in err.splitlines():
            try:failure=json.loads(line)
            except (ValueError,UnicodeError):continue
            if type(failure) is dict and failure.get('phase')=='history_unit_acceptance_stopped':
                print(json.dumps(failure),file=sys.stderr)
        raise ValueError('unit acceptance stopped; preserve evidence')
    answer=json.loads(out)
    if answer.get('phase')!='isolated_history_hardened_unit_verified' or answer.get('api_calls')!=0:raise ValueError('unexpected unit result')
    answer.update(acceptance_release=str(release),manifest_sha256=expected,source_commit=manifest['source_commit'])
    return answer


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate',required=True);parser.add_argument('--manifest-sha256',required=True)
    args=parser.parse_args()
    try:print(json.dumps(stage(args.candidate,args.manifest_sha256),indent=2))
    except Exception:
        sys.stderr.write('Hardened unit acceptance stopped; preserve fixture evidence. No automatic retry.\n');raise SystemExit(1)
