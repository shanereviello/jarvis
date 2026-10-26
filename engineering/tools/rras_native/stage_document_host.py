"""Stdlib-only root bootstrap appended to the pinned fixture verifier."""
import argparse
import os
import subprocess
import sys

PYTHON=Path('/opt/rras-engineering/releases/native-10/venv/bin/python')


def protected(path):
    for item in (path,*path.parents):
        info=item.lstat()
        if item.is_symlink() or info.st_uid!=0 or info.st_mode&0o022:raise ValueError('root-protected fixture path required')


def write(path,raw,mode):
    with path.open('xb') as stream:
        os.fchmod(stream.fileno(),mode);stream.write(raw);stream.flush();os.fsync(stream.fileno())


def stage(candidate,expected):
    if os.getuid()!=0 or os.geteuid()!=0:raise ValueError('explicit sudo fixture invocation required')
    if type(expected) is not str or not re.fullmatch('[0-9a-f]{64}',expected):raise ValueError('exact fixture digest required')
    release=Path('/opt/rras-engineering/releases/document-approval-acceptance-'+expected[:12])
    for path in (release.parent,STATE.parent,DIAGNOSTICS.parent,PYTHON.resolve(strict=True)):protected(path)
    for path in (release,STATE,DIAGNOSTICS):
        if path.exists() or path.is_symlink():raise ValueError('preserve existing fixture; no automatic retry')
    manifest,files=verify(candidate,expected)
    os.umask(0o022);release.mkdir(mode=0o755)
    for name,raw in files.items():
        path=release/name;path.parent.mkdir(mode=0o755,parents=True,exist_ok=True);write(path,raw,0o444)
    write(release/MANIFEST,encoded(manifest),0o444)
    for directory in sorted([release,*[p for p in release.rglob('*') if p.is_dir()]],key=lambda p:len(p.parts),reverse=True):
        fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
    DIAGNOSTICS.mkdir(mode=0o700)
    with (DIAGNOSTICS/'stdout.json').open('xb') as out,(DIAGNOSTICS/'stderr.txt').open('xb') as err:
        os.fchmod(out.fileno(),0o600);os.fchmod(err.fileno(),0o600)
        try:
            result=subprocess.run([str(PYTHON),'-I','-B',str(release/'engineering/tools/rras_native/probe_document_approval.py')],
                env={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','LANG':'C.UTF-8'},stdin=subprocess.DEVNULL,
                stdout=out,stderr=err,timeout=480)
        finally:
            for stream in (out,err):stream.flush();os.fsync(stream.fileno())
    if result.returncode:raise ValueError('document host fixture failed; private diagnostic saved')
    answer=decode(regular(DIAGNOSTICS/'stdout.json',1024*1024))
    if (answer.get('phase')!='isolated_document_approval_host_verified' or answer.get('api_calls')!=0 or
            answer.get('production_unit_used') is not False):raise ValueError('fixture result differs')
    answer.update(acceptance_release=str(release),manifest_sha256=expected,source_commit=manifest['source_commit'])
    write(DIAGNOSTICS/'result.json',encoded(answer),0o600)
    return answer


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate',required=True);parser.add_argument('--manifest-sha256',required=True)
    args=parser.parse_args()
    try:print(json.dumps(stage(Path(args.candidate),args.manifest_sha256),indent=2))
    except Exception:
        sys.stderr.write('Document approval host acceptance stopped; preserve protected fixture and diagnostics. No automatic retry.\n')
        raise SystemExit(1)
