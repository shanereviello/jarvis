"""Protected one-shot catalog writer launch; never installs or retries a unit."""
import argparse
import hashlib
import os
import pwd
import grp
from pathlib import Path
import re
import stat
import subprocess
import sys

ENV={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','LANG':'C.UTF-8'}
REQUESTS=Path('/var/lib/rras-curated-publications/requests')
ATTEMPTS=Path('/var/lib/rras-curated-publications/attempts')
CATALOG='/var/lib/rras-curated-history/catalog'
PYTHON='/opt/rras-engineering/releases/native-10/venv/bin/python'
LIMIT=2*1024*1024


def digest(value):
    if type(value) is not str or not re.fullmatch('[0-9a-f]{64}',value):raise ValueError('exact request digest required')
    return value


def command(release,sha):
    digest(sha)
    if type(release) is not str or not re.fullmatch('/opt/rras-engineering/releases/curated-history-[0-9a-f]{12}',release):
        raise ValueError('fixed protected release required')
    properties=[
        'User=rras-history','Group=rras-history','SupplementaryGroups=',
        'UMask=0077','ProtectSystem=strict','ProtectHome=yes',
        'ReadWritePaths='+CATALOG,
        'InaccessiblePaths=-/var/lib/rras-engineering-history -/etc/rras-engineering-history -/run/rras-engineering-history -/var/lib/rras-workflow -/var/lib/rras-coding-control -/var/lib/rras-coding-tasks -/opt/rras-coding-jobs -/etc/rras-engineering/credentials -/run/docker.sock -/run/rras-curated-history -/var/lib/rras-curated-publications',
        'PrivateNetwork=yes','RestrictAddressFamilies=AF_UNIX','PrivateTmp=yes','PrivateDevices=yes',
        'NoNewPrivileges=yes','CapabilityBoundingSet=','AmbientCapabilities=',
        'ProtectKernelTunables=yes','ProtectKernelModules=yes','ProtectKernelLogs=yes',
        'ProtectControlGroups=yes','ProtectClock=yes','ProtectProc=invisible','ProcSubset=pid',
        'RestrictNamespaces=yes','RestrictSUIDSGID=yes','RestrictRealtime=yes','LockPersonality=yes',
        'MemoryDenyWriteExecute=yes','SystemCallArchitectures=native','SystemCallFilter=@system-service',
        'SystemCallErrorNumber=EPERM','TasksMax=16','MemoryMax=512M','LimitNOFILE=64',
        'RuntimeMaxSec=60s','TimeoutStopSec=5s','KillMode=control-group','Restart=no',
        'WorkingDirectory='+release,
    ]
    argv=['/usr/bin/systemd-run','--system','--quiet','--wait','--pipe','--collect',
          '--unit=rras-curated-publication.service','--service-type=exec']
    for prop in properties:argv.extend(['--property',prop])
    argv.extend(['--','/usr/bin/env','-i','PATH=/usr/bin:/bin','HOME=/nonexistent','LANG=C.UTF-8',
                 PYTHON,'-I','-B',release+'/engineering/tools/rras_history/curated_publication_entry.py',
                 '--reviewed-request-sha256',sha])
    return argv


def protected(path):
    path=Path(path)
    if not path.is_absolute() or path.resolve(strict=True)!=path:raise ValueError('canonical protected path required')
    for item in (path,*path.parents):
        info=item.lstat()
        if stat.S_ISLNK(info.st_mode) or info.st_uid!=0 or info.st_mode&0o022:
            raise ValueError('root-owned protected path required')
    return path.lstat()


def preflight(release,sha):
    argv=command(release,sha)
    if os.getuid()!=0 or os.geteuid()!=0:raise ValueError('explicit administrator invocation required')
    # Root never imports candidate code. Protect every payload/dependency entry,
    # including directories, before asking systemd to execute it as UID 995.
    account=pwd.getpwnam('rras-history');group=grp.getgrnam('rras-history')
    if account.pw_uid!=995 or account.pw_gid!=995 or group.gr_gid!=995 or set(os.getgrouplist(account.pw_name,995))!={995}:
        raise ValueError('dedicated catalog owner identity differs')
    root=Path(release);protected(root)
    entry=root/'engineering/tools/rras_history/curated_publication_entry.py'
    if not stat.S_ISREG(protected(entry).st_mode):raise ValueError('protected writer entry required')
    for item in root.rglob('*'):
        info=protected(item)
        if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):raise ValueError('ordinary protected payload required')
    protected(Path(PYTHON).parent)
    for executable in (Path(PYTHON).resolve(strict=True),Path('/usr/bin/systemd-run'),Path('/usr/bin/env')):protected(executable)
    protected(ATTEMPTS)
    request=REQUESTS/(sha+'.json');info=protected(request)
    if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode)!=0o600 or info.st_nlink!=1 or info.st_size>LIMIT:
        raise ValueError('private bounded protected request required')
    fd=os.open(request,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as stream:
        opened=os.fstat(stream.fileno())
        if (opened.st_dev,opened.st_ino)!=(info.st_dev,info.st_ino):raise ValueError('request changed')
        raw=stream.read(LIMIT+1)
    if len(raw)>LIMIT or hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('exact protected request differs')
    return argv,raw


def launch(release,sha):
    argv,raw=preflight(release,sha)
    # An exclusive protected attempt fence survives success, timeout or lost reply.
    # Even catalog-idempotent requests require diagnosis before another launch.
    attempt=ATTEMPTS/sha;attempt.mkdir(mode=0o700)
    fd=os.open(attempt/'started',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream:
        stream.write((release+'\n'+sha+'\n').encode());stream.flush();os.fsync(stream.fileno())
    for path in (attempt,ATTEMPTS):
        fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
    result=subprocess.run(argv,input=raw,capture_output=True,env=ENV,timeout=75)
    # Preserve raw diagnostics privately, never forward catalog prose to root CLI.
    for name,value in (('stdout',result.stdout),('stderr',result.stderr),('returncode',str(result.returncode).encode())):
        fd=os.open(attempt/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as stream:stream.write(value);stream.flush();os.fsync(stream.fileno())
    if result.returncode:raise ValueError('writer did not return success; preserve evidence')
    return {'writer_returned':True,'publication_verified':False,'automatic_retry':False}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release',required=True);parser.add_argument('--reviewed-request-sha256',required=True)
    args=parser.parse_args(argv)
    try:
        launch(args.release,args.reviewed_request_sha256)
        print('{"writer_returned":true,"publication_verified":false,"automatic_retry":false}')
    except (ValueError,OSError,subprocess.SubprocessError):
        parser.exit(1,'Publication launch stopped; preserve protected attempt and catalog evidence. No automatic retry.\n')


if __name__=='__main__':main()
