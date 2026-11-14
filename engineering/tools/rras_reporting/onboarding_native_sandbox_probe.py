"""Model-free native App Server isolation probe in disposable workspaces.

Run only from a protected root-side proof producer. This never sends a model
turn, accesses an existing checkout, or changes production service units.
"""
import hashlib
import json
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import tempfile


CHILD = '''import importlib.util,json,sys
from pathlib import Path
runtime,binary,own,other=map(Path,sys.argv[1:]);home=own/'fixture-home'
s=importlib.util.spec_from_file_location('runtime',runtime);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
client=m.AppServer(str(binary),str(own),timeout=30,codex_home=home)
try:
 t=client.call('thread/start',dict(cwd=str(own),sandbox='workspace-write',approvalPolicy='on-request',ephemeral=True,config={'analytics.enabled':False,'check_for_update_on_startup':False}))['thread']
 code="from pathlib import Path\\nimport sys,errno\\na,b=map(Path,sys.argv[1:]);(a/'own-check').write_text('fixture')\\ntry:(b/'other-check').write_text('forbidden')\\nexcept OSError as e:\\n if e.errno not in (errno.EACCES,errno.EPERM,errno.EROFS):raise\\n print('own_allowed sibling_denied')\\nelse:raise SystemExit('sibling write unexpectedly allowed')"
 x=client.call('command/exec',dict(command=['/usr/bin/python3','-I','-c',code,str(own),str(other)],cwd=str(own),sandboxPolicy=dict(type='workspaceWrite',networkAccess=False,writableRoots=[])))
 if t.get('cwd')!=str(own) or x.get('exitCode')!=0 or 'own_allowed sibling_denied' not in x.get('stdout',''):raise ValueError('isolation probe failed')
 print(json.dumps({'native_identity_verified':True,'sandbox_own_write_allowed':True,'sandbox_sibling_write_denied':True,'models_started':0}))
finally:client.close()
'''


def digest(path):
    sha = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):sha.update(chunk)
    return sha.hexdigest()


def probe(expected):
    if os.getuid() != 0 or os.geteuid() != 0:
        raise ValueError('root native sandbox probe required')
    release = Path(expected['native_release'])
    binary = release / 'runtime/bin/codex'
    python = release / 'venv/bin/python'
    runtime = release / 'engineering/tools/rras_reporting/codex_runtime.py'
    if (not release.is_absolute() or release.resolve() != release or binary.resolve() != binary or
            digest(binary) != expected['native_binary_sha256'] or not python.is_file() or not runtime.is_file()):
        raise ValueError('exact native release and binary required')
    account = pwd.getpwnam('rras-codex-native')
    root = Path(tempfile.mkdtemp(prefix='rras-native-sandbox-proof-',dir='/srv'))
    try:
        os.chown(root,account.pw_uid,account.pw_gid);root.chmod(0o700)
        own,other = root/'own',root/'sibling'
        for path in (own,other):
            path.mkdir(mode=0o700);os.chown(path,account.pw_uid,account.pw_gid)
        home = own/'fixture-home';home.mkdir(mode=0o700);os.chown(home,account.pw_uid,account.pw_gid)
        direct = "from pathlib import Path;import sys\nfor p in sys.argv[1:]:\n q=Path(p)/'direct-check';q.write_text('x');q.unlink()"
        drop = ['/usr/bin/setpriv','--reuid='+str(account.pw_uid),'--regid='+str(account.pw_gid),
            '--clear-groups','--no-new-privs','--bounding-set=-all','--inh-caps=-all','--ambient-caps=-all']
        subprocess.run(drop+['/usr/bin/python3','-I','-c',direct,str(own),str(other)],
            env={'PATH':'/usr/bin:/bin','HOME':'/nonexistent'},capture_output=True,check=True,timeout=20)
        command = ['/usr/bin/systemd-run','--wait','--pipe','--collect',
            '--property=User=rras-codex-native','--property=Group=rras-codex-native',
            '--property=NoNewPrivileges=yes','--property=CapabilityBoundingSet=','--property=AmbientCapabilities=',
            '--property=PrivateTmp=yes','--property=PrivateDevices=yes','--property=PrivateNetwork=yes',
            '--property=ProtectHome=yes','--property=ProtectSystem=strict','--property=ProtectKernelTunables=yes',
            '--property=ProtectKernelModules=yes','--property=ProtectControlGroups=yes','--property=ProtectClock=yes',
            '--property=LockPersonality=yes','--property=RestrictSUIDSGID=yes',
            '--property=RestrictAddressFamilies=AF_UNIX AF_NETLINK','--property=ReadWritePaths='+str(own),
            '--property=WorkingDirectory='+str(own),'/usr/bin/env','-i','PATH=/usr/bin:/bin',
            'HOME='+str(home),'CODEX_HOME='+str(home),str(python),'-I','-c',CHILD,
            str(runtime),str(binary),str(own),str(other)]
        result = subprocess.run(command,capture_output=True,text=True,timeout=90)
        if result.returncode != 0 or (other/'other-check').exists() or digest(binary) != expected['native_binary_sha256']:
            raise ValueError('native sandbox probe failed or binary changed')
        lines = result.stdout.strip().splitlines()
        value = json.loads(lines[-1]) if lines else None
        if value != {'native_identity_verified':True,'sandbox_own_write_allowed':True,
                     'sandbox_sibling_write_denied':True,'models_started':0}:
            raise ValueError('native sandbox probe result differs')
        return value
    finally:
        shutil.rmtree(root)
