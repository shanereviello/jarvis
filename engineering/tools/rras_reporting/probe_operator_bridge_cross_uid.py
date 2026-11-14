"""Model-free, network-isolated operator/browser Unix peer fixture."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import uuid

ROOT=Path(__file__).resolve().parents[2]
IMAGE='sha256:b99f4564d5e17ec0183314c0d2f6f633657cff4916fad0f05f6e7667722da432'
BASE=Path('/tmp/rras-operator-cross');OPERATOR=61183;BROWSER=61184;ROGUE=61185;SOCKET=BASE/'socket'/'operator.sock'


def local(name):
    spec=importlib.util.spec_from_file_location('operator_cross_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def drop(uid):os.setgroups([]);os.setgid(BROWSER);os.setuid(uid)


def operator():
    bridge=local('onboarding_operator_browser_unix');transport=local('onboarding_broker_unix');stop=threading.Event()
    class Browser:
        def begin(self,headers,review,comment):
            if headers!=[(b'origin',b'https://fixture.test')] or (review,comment)!=('review','comment'):raise ValueError('fixture input differs')
            return dict(challenge='fixture',execution_authorized=False)
        def confirm(self,*_):raise ValueError('unused fixture operation')
    with transport.server(SOCKET,bridge.Broker(BROWSER,Browser())) as server:
        def loop():
            while not stop.is_set():server.serve_once()
        worker=threading.Thread(target=loop);worker.start();print('ready',flush=True)
        try:
            if sys.stdin.readline().strip()!='stop':raise ValueError('fixture coordination failed')
        finally:stop.set();worker.join(5)


def client(rogue):
    bridge=local('onboarding_operator_browser_unix')
    try:(BASE/'private'/'evidence').read_text()
    except PermissionError:pass
    else:raise ValueError('unprivileged peer accessed private operator evidence')
    try:result=bridge.Client(SOCKET,OPERATOR).begin([(b'origin',b'https://fixture.test')],'review','comment')
    except (ValueError,OSError):
        if not rogue:raise
    else:
        if rogue or result!={'challenge':'fixture','execution_authorized':False}:raise ValueError('peer check failed')


def inside():
    if not Path('/.dockerenv').exists() or os.getuid()!=0:raise ValueError('isolated root fixture required')
    if {line.split(':',1)[0].strip() for line in Path('/proc/self/net/dev').read_text().splitlines() if ':' in line}!={'lo'}:
        raise ValueError('network-isolated fixture required')
    BASE.mkdir(mode=0o755)
    for name,mode in [('socket',0o710),('private',0o700)]:
        path=BASE/name;path.mkdir(mode=mode)
        if name=='private':
            data=path/'evidence';data.write_text('fixture');data.chmod(0o600);os.chown(data,OPERATOR,BROWSER)
        os.chown(path,OPERATOR,BROWSER)
    env=dict(PATH='/usr/bin:/bin',HOME='/nonexistent',LANG='C.UTF-8')
    process=subprocess.Popen([sys.executable,'-I','-B',__file__,'--role','operator'],preexec_fn=lambda:drop(OPERATOR),env=env,
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        if process.stdout.readline().strip()!='ready':raise ValueError('operator bridge failed: '+process.stderr.read()[-2000:])
        for role,uid in [('browser',BROWSER),('rogue',ROGUE)]:
            result=subprocess.run([sys.executable,'-I','-B',__file__,'--role',role],preexec_fn=lambda:drop(uid),env=env,capture_output=True,text=True,timeout=15)
            if result.returncode:raise ValueError('peer fixture failed: '+result.stderr[-2000:])
        process.stdin.write('stop\n');process.stdin.flush();_,error=process.communicate(timeout=15)
        if process.returncode:raise ValueError('operator fixture failed: '+error[-2000:])
        print(json.dumps(dict(distinct_numeric_uids=True,allowed_browser_verified=True,wrong_peer_denied=True,
            private_operator_evidence_denied=True,network_isolated=True,models_started=0)))
    finally:
        if process.poll() is None:process.kill();process.wait()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--role',choices=('inside','operator','browser','rogue'))
    parser.add_argument('--isolated-containers',action='store_true');args=parser.parse_args()
    if args.role=='inside':inside();return
    if args.role=='operator':operator();return
    if args.role in ('browser','rogue'):client(args.role=='rogue');return
    if not args.isolated_containers:parser.error('explicit isolated fixture required')
    name='rras-operator-cross-'+uuid.uuid4().hex[:10]
    command=['docker','run','--rm','--name',name,'--pull=never','--network','none','--read-only','--cap-drop','ALL',
        '--cap-add','SETUID','--cap-add','SETGID','--cap-add','CHOWN','--cap-add','KILL','--security-opt','no-new-privileges:true',
        '--tmpfs','/tmp:rw,nosuid,nodev,size=64m,mode=1777','--mount','type=bind,source='+str(ROOT)+',target=/fixture/engineering,readonly',
        '--user','0:0','--entrypoint','/usr/bin/env',IMAGE,'-i','PATH=/usr/bin:/bin','HOME=/nonexistent','LANG=C.UTF-8',
        '/opt/hermes/.venv/bin/python','-I','-B','/fixture/engineering/tools/rras_reporting/probe_operator_bridge_cross_uid.py','--role','inside']
    try:
        result=subprocess.run(command,capture_output=True,text=True,timeout=60)
        if result.returncode:raise ValueError('offline operator fixture failed: '+result.stderr[-3000:])
        print(result.stdout.strip())
    finally:subprocess.run(['docker','rm','-f',name],capture_output=True,timeout=15)


if __name__=='__main__':main()
