"""Stdlib-only pinned bootstrap for an isolated fixture, never production install.

This file is copied with its verifier into one self-contained operator helper.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

# Verifier functions are inserted above this line in the emitted operator helper.


def protected(path):
    for p in (path,*path.parents):
        info=p.lstat()
        if p.is_symlink() or info.st_uid!=0 or info.st_mode&0o022:
            raise ValueError('root-owned protected fixture destination required')


def stage(candidate,expected,state):
    if os.getuid()!=0 or os.geteuid()!=0:raise ValueError('reviewed sudo invocation required')
    state=Path(state)
    if state!=Path('/var/lib/rras-history-acceptance-20261022'):raise ValueError('exact acceptance fixture required')
    release=Path('/opt/rras-engineering/releases/history-acceptance-'+expected[:12])
    python=Path('/opt/rras-engineering/releases/native-10/venv/bin/python')
    protected(release.parent);protected(state.parent);protected(python.parent);protected(python.resolve(strict=True))
    if release.exists() or release.is_symlink() or state.exists() or state.is_symlink():
        raise ValueError('fixture/release exists; preserve evidence, no retry')
    manifest,files=verify(candidate,expected)
    os.umask(0o022);release.mkdir(mode=0o755)
    for name,content in files.items():
        target=release/name;target.parent.mkdir(mode=0o755,parents=True,exist_ok=True)
        with target.open('xb') as stream:
            os.fchmod(stream.fileno(),0o444);stream.write(content);stream.flush();os.fsync(stream.fileno())
    with (release/'acceptance-manifest.json').open('xb') as stream:
        os.fchmod(stream.fileno(),0o444);stream.write(encoded(manifest));stream.flush();os.fsync(stream.fileno())
    for path in sorted({release,*[p.parent for p in release.rglob('*')]},key=lambda p:len(p.parts),reverse=True):
        os.chmod(path,0o755)
        fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
    process=subprocess.Popen(['/usr/bin/python3','-I','-B',str(release/'engineering/tools/rras_history/host_acceptance.py'),str(state)],
                             env={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','LANG':'C.UTF-8'},stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:out,err=process.communicate(timeout=240)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:process.communicate(timeout=20)
        except subprocess.TimeoutExpired:process.kill();process.communicate(timeout=5)
        raise ValueError('isolated acceptance timeout; preserve protected evidence')
    if process.returncode:raise ValueError('isolated acceptance failed; preserve protected evidence')
    answer=json.loads(out)
    if answer.get('phase')!='isolated_history_cross_uid_verified' or answer.get('api_calls')!=0:
        raise ValueError('unexpected acceptance outcome')
    answer.update(acceptance_release=str(release),manifest_sha256=expected,source_commit=manifest['source_commit'])
    return answer


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate',required=True);parser.add_argument('--manifest-sha256',required=True)
    parser.add_argument('--state',required=True)
    args=parser.parse_args(argv)
    try:print(json.dumps(stage(args.candidate,args.manifest_sha256,args.state),indent=2))
    except Exception:
        sys.stderr.write('History acceptance stopped; preserve protected fixture/release evidence. No automatic retry.\n')
        raise SystemExit(1)


if __name__=='__main__':main()
