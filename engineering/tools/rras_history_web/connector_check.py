"""Root-run, bounded synthetic bridge-route rehearsal; no production route/config."""
import argparse
import grp
import hashlib
import json
import os
from pathlib import Path
import pwd
import signal
import socket
import stat
import subprocess
import sys
import time

STATE=Path('/var/lib/rras-history-web-route-check-attempt02-20261104')
PYTHON=Path('/opt/rras-engineering/releases/cpython-3.13.16-ae7041461525/bin/python3.13')
NETWORK='jarvis-net'
BIND='172.19.0.1'
PORT=18764
HOST='jarvis-coding.reviellorobotics.com'
IMAGE='sha256:b99f4564d5e17ec0183314c0d2f6f633657cff4916fad0f05f6e7667722da432'
CONTAINER='rras-history-web-route-check-attempt02-20261104'
LABEL='rras.fixture=history-web-route-check-attempt02-20261104'
UID=61167
ENV={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','LANG':'C.UTF-8'}

SERVER=r'''
import ctypes,http.server,json,os,signal,sys
if os.getuid()!=61167 or os.geteuid()!=61167 or os.getgid()!=61167 or os.getegid()!=61167 or os.getgroups():raise ValueError('fixture identity differs')
status=dict(line.split(':',1) for line in open('/proc/self/status').read().splitlines() if ':' in line)
if status['NoNewPrivs'].strip()!='1' or any(int(status[k].strip(),16) for k in ('CapInh','CapPrm','CapEff','CapBnd','CapAmb')):raise ValueError('fixture privileges retained')
if set(os.environ)-{'PATH','HOME','LANG'}:raise ValueError('fixture environment differs')
parent=os.getppid()
if parent<=1:raise ValueError('fixture parent absent')
if ctypes.CDLL(None,use_errno=True).prctl(1,signal.SIGTERM,0,0,0)!=0 or os.getppid()!=parent:raise ValueError('fixture parent differs')
signal.alarm(45)
nonce=sys.argv[1]
class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        allowed=self.path=='/rras-route-check' and self.headers.get_all('Host')==['jarvis-coding.reviellorobotics.com']
        raw=json.dumps({'synthetic_route_check':True,'nonce':nonce} if allowed else {'refused':True}).encode()
        self.send_response(200 if allowed else 403);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def log_message(self,*args):pass
http.server.HTTPServer(('172.19.0.1',18764),Handler).serve_forever(poll_interval=0.1)
'''

CLIENT=r'''
import http.client,json,os,sys
value=json.load(sys.stdin)
identity=dict(uid=os.getuid(),euid=os.geteuid(),gid=os.getgid(),egid=os.getegid(),groups=os.getgroups())
if any(identity[name]!=61167 for name in ('uid','euid','gid','egid')) or set(identity['groups'])-{61167}:raise ValueError('client identity differs: '+json.dumps(identity))
if set(os.environ)-{'PATH','HOME','LANG'}:raise ValueError('client environment differs')
status=dict(line.split(':',1) for line in open('/proc/self/status').read().splitlines() if ':' in line)
if status['NoNewPrivs'].strip()!='1' or any(int(status[k].strip(),16) for k in ('CapInh','CapPrm','CapEff','CapBnd','CapAmb')):raise ValueError('client privileges retained')
for host,wanted in [('jarvis-coding.reviellorobotics.com',200),('wrong.example.test',403)]:
    c=http.client.HTTPConnection('172.19.0.1',18764,timeout=3);c.request('GET','/rras-route-check',headers={'Host':host});r=c.getresponse();body=r.read(4097)
    if r.status!=wanted:raise ValueError('route response differs')
    if wanted==200 and json.loads(body)!={'synthetic_route_check':True,'nonce':value['nonce']}:raise ValueError('route identity differs')
    c.close()
print(json.dumps({'docker_bridge_route_verified':True,'exact_host_header_verified':True,'wrong_host_refused':True,'credentials_used':False}))
'''


def command(argv,raw=None,timeout=15):return subprocess.run(argv,input=raw,capture_output=True,timeout=timeout,cwd='/',env=ENV)


def checked(argv,raw=None,timeout=15):
    result=command(argv,raw,timeout)
    if result.returncode:raise ValueError('route fixture command refused')
    return result.stdout


def protected(path):
    for item in (path,*path.parents):
        info=item.lstat()
        if item.is_symlink() or info.st_uid!=0 or info.st_mode&0o022:raise ValueError('protected fixture input required')


def write(path,raw,mode=0o600):
    with path.open('xb') as stream:os.fchmod(stream.fileno(),mode);stream.write(raw);stream.flush();os.fsync(stream.fileno())


def client_command():
    return ['/usr/bin/docker','run','--rm','--pull=never','--name',CONTAINER,'--label',LABEL,'--network',NETWORK,
        '--read-only','--cap-drop=ALL','--security-opt=no-new-privileges:true','--user','61167:61167','--stop-timeout','3','-i',
        '--entrypoint','/usr/bin/env',IMAGE,'-i','PATH=/usr/bin:/bin','HOME=/nonexistent','LANG=C.UTF-8',
        '/opt/hermes/.venv/bin/python','-I','-S','-B','-c',CLIENT]


def absent():
    result=command(['/usr/bin/docker','container','ls','-aq','--filter','name=^/'+CONTAINER+'$'])
    if result.returncode:raise ValueError('fixture container inventory refused')
    return not result.stdout.strip()


def cleanup_container():
    if absent():return
    label=checked(['/usr/bin/docker','inspect','--format','{{index .Config.Labels "rras.fixture"}}',CONTAINER]).decode().strip()
    if label!=LABEL.split('=',1)[1]:raise ValueError('fixture container label differs; do not remove')
    checked(['/usr/bin/docker','stop','--time','3',CONTAINER])
    if not absent():raise ValueError('fixture container retained')


def run():
    if os.getuid()!=0 or os.geteuid()!=0:raise ValueError('explicit sudo route rehearsal required')
    protected(STATE.parent);protected(PYTHON)
    if STATE.exists() or STATE.is_symlink():raise ValueError('preserve existing route evidence; no retry')
    for lookup in (pwd.getpwuid,grp.getgrgid):
        try:lookup(UID)
        except KeyError:pass
        else:raise ValueError('route fixture identity occupied')
    for path in Path('/proc').glob('[0-9]*/status'):
        try:lines=path.read_text().splitlines()
        except (FileNotFoundError,ProcessLookupError):continue
        if any(line.startswith(('Uid:','Gid:')) and str(UID) in line.split()[1:] for line in lines):raise ValueError('route fixture identity active')
    if not absent():raise ValueError('existing fixture container; preserve state')
    network=checked(['/usr/bin/docker','inspect','cloudflared','--format','{{.HostConfig.NetworkMode}}']).decode().strip()
    ipam=json.loads(checked(['/usr/bin/docker','network','inspect',NETWORK,'--format','{{json .IPAM.Config}}']))
    if network!=NETWORK or ipam!=[{'Subnet':'172.19.0.0/16','Gateway':BIND}]:raise ValueError('connector network baseline changed')
    if checked(['/usr/bin/docker','image','inspect','--format','{{.Id}}',IMAGE]).decode().strip()!=IMAGE:raise ValueError('pinned fixture image unavailable')
    with socket.socket() as test:test.bind((BIND,PORT))
    os.umask(0o077);STATE.mkdir(mode=0o711);STATE.chmod(0o711);(STATE/'private').mkdir(mode=0o700)
    write(STATE/'server.py',SERVER.encode(),0o444)
    nonce=os.urandom(24).hex();process=None;result=None
    try:
        process=subprocess.Popen(['/usr/bin/setpriv','--reuid',str(UID),'--regid',str(UID),'--clear-groups','--no-new-privs',
            '--bounding-set=-all','--inh-caps=-all','--ambient-caps=-all',str(PYTHON),'-I','-S','-B',str(STATE/'server.py'),nonce],
            stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=ENV,cwd='/',start_new_session=True)
        for _ in range(50):
            if process.poll() is not None:raise ValueError('synthetic route server exited')
            with socket.socket() as test:
                test.settimeout(0.2)
                if test.connect_ex((BIND,PORT))==0:break
            time.sleep(0.1)
        else:raise ValueError('synthetic route listener unavailable')
        client=command(client_command(),json.dumps({'nonce':nonce}).encode(),timeout=20)
        write(STATE/'private/client-stdout.json',client.stdout);write(STATE/'private/client-stderr.txt',client.stderr)
        if client.returncode:raise ValueError('Docker route probe stopped; preserve evidence')
        value=json.loads(client.stdout)
        if value.get('docker_bridge_route_verified') is not True or value.get('exact_host_header_verified') is not True or value.get('wrong_host_refused') is not True:raise ValueError('unexpected route result')
        result=dict(phase='synthetic_connector_bridge_route_verified',journal=str(STATE),origin='http://172.19.0.1:18764',
            cases=['pinned_unprivileged_no_volume_client_on_connector_network','synthetic_host_bridge_origin_reached','exact_host_header_and_nonce','wrong_host_refused'],
            real_dashboard_started=False,private_history_contacted=False,existing_containers_mutated=False,cloudflare_changed=False,
            real_credentials_used=False,model_api_calls=0,accounts_created=False,automatic_retry=False)
    finally:
        try:cleanup_container()
        finally:
            if process is not None:
                if process.poll() is None:os.killpg(process.pid,signal.SIGTERM)
                try:out,err=process.communicate(timeout=5)
                except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);out,err=process.communicate(timeout=5)
                write(STATE/'private/server-stdout.txt',out);write(STATE/'private/server-stderr.txt',err)
    if not absent():raise ValueError('route fixture container retained')
    with socket.socket() as test:
        test.settimeout(1)
        if test.connect_ex((BIND,PORT))==0:raise ValueError('route fixture listener retained')
    result.update(fixture_listener_stopped=True,fixture_container_removed=True)
    write(STATE/'private/result.json',json.dumps(result,sort_keys=True).encode())
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.parse_args()
    try:print(json.dumps(run(),indent=2))
    except Exception:
        sys.stderr.write('Synthetic connector route check stopped; preserve fixture evidence. No automatic retry.\n');raise SystemExit(1)
