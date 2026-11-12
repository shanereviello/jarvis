"""Start the inactive operator entry with temporary UIDs in an offline container."""
import argparse
import json
import os
from pathlib import Path
import signal
import socket
import stat
import subprocess
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[2]
IMAGE='sha256:b99f4564d5e17ec0183314c0d2f6f633657cff4916fad0f05f6e7667722da432'
BASE=Path('/tmp/rras-operator-entry');OPERATOR=61183;PLANNER=61180;BROWSER=61184;ROGUE=61185;HISTORY=61190
uid=lambda n:f'00000000-0000-4000-8000-{n:012d}'


def drop(user):os.setgroups([]);os.setgid(user);os.setuid(user)


def inside():
    if not Path('/.dockerenv').exists() or os.getuid()!=0:raise ValueError('isolated root fixture required')
    if {line.split(':',1)[0].strip() for line in Path('/proc/self/net/dev').read_text().splitlines() if ':' in line}!={'lo'}:
        raise ValueError('network-isolated fixture required')
    BASE.mkdir(mode=0o755);config_dir=BASE/'config';config_dir.mkdir(mode=0o755)
    state_parent=BASE/'state';state_parent.mkdir(mode=0o700);os.chown(state_parent,OPERATOR,OPERATOR)
    for name in ('review','browser'):
        path=BASE/name;path.mkdir(mode=0o700);os.chown(path,OPERATOR,OPERATOR)
    app=uid(2);base_url='http://127.0.0.1:5678/webhook/'
    value=dict(operator_uid=OPERATOR,operator_gid=OPERATOR,planning_peer_uid=PLANNER,browser_peer_uid=BROWSER,history_uid=HISTORY,
        history_socket=str(BASE/'history.sock'),review_socket=str(BASE/'review'/'review.sock'),browser_socket=str(BASE/'browser'/'browser.sock'),
        organization_id=uid(1),app_user_id=app,team_id=uid(3),human_ids=[uid(4)],scopes=[{'kind':'repository','id':'fixture'}],
        reader_origin_url=base_url+'rras-planning-origin-'+app,reader_issue_url=base_url+'rras-planning-issue-'+app,
        comment_url=base_url+'rras-operator-comment-'+app,
        access=dict(issuer='https://fixture.cloudflareaccess.com',audience='fixture',email='owner@example.test',origin='https://fixture.example.test'))
    for name,content in [('config.json',json.dumps(value)),('planning-token','p'*48),('comment-token','c'*48)]:
        path=config_dir/name;path.write_text(content);path.chmod(0o640);os.chown(path,0,OPERATOR)
    entry='/fixture/engineering/tools/rras_reporting/onboarding_operator_entry.py';state=state_parent/'journal'
    args=[sys.executable,'-I','-B',entry,'--config',str(config_dir/'config.json'),'--state',str(state),
          '--planning-token',str(config_dir/'planning-token'),'--comment-token',str(config_dir/'comment-token')]
    env=dict(PATH='/usr/bin:/bin',HOME='/nonexistent',LANG='C.UTF-8')
    init=subprocess.run([*args,'--initialize'],preexec_fn=lambda:drop(OPERATOR),env=env,capture_output=True,text=True,timeout=20)
    if init.returncode or not json.loads(init.stdout)['initialized']:raise ValueError('operator initialization failed: '+init.stderr[-1000:])
    process=subprocess.Popen(args,preexec_fn=lambda:drop(OPERATOR),env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
    try:
        sockets=[BASE/'review'/'review.sock',BASE/'browser'/'browser.sock']
        for _ in range(100):
            if process.poll() is not None:raise ValueError('operator entry exited: '+process.stderr.read()[-1000:])
            if all(path.exists() for path in sockets):break
            time.sleep(.05)
        else:raise ValueError('operator sockets unavailable')
        for path in sockets:
            info=path.lstat()
            if not stat.S_ISSOCK(info.st_mode) or info.st_uid!=OPERATOR:raise ValueError('socket ownership differs')
        # Browser is permitted by the ACL but still cannot ask for a general
        # history method; a rogue UID cannot connect to either socket.
        helper='''import socket,sys\ns=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)\ntry:s.connect(sys.argv[1])\nexcept OSError:sys.exit(2)\ns.close()\n'''
        def connect(user,path):
            return subprocess.run([sys.executable,'-I','-c',helper,str(path)],preexec_fn=lambda:drop(user),env=env,capture_output=True,timeout=10).returncode
        if connect(BROWSER,sockets[1])!=0 or connect(PLANNER,sockets[0])!=0:raise ValueError('configured peer ACL refused')
        if connect(ROGUE,sockets[0])!=2 or connect(ROGUE,sockets[1])!=2:raise ValueError('rogue socket ACL allowed')
        private='''from pathlib import Path\nimport sys\ntry:Path(sys.argv[1]).read_bytes()\nexcept PermissionError:sys.exit(0)\nsys.exit(1)\n'''
        if subprocess.run([sys.executable,'-I','-c',private,str(state/'operator.sqlite3')],preexec_fn=lambda:drop(BROWSER),env=env,timeout=10).returncode:
            raise ValueError('browser read operator journal')
        process.send_signal(signal.SIGTERM);process.wait(timeout=15)
        if process.returncode or any(path.exists() for path in sockets):raise ValueError('operator shutdown or socket cleanup failed')
        print(json.dumps(dict(actual_entry_initialized=True,operator_active_then_stopped=True,distinct_numeric_uids=True,
            configured_peer_acls_verified=True,rogue_acl_denied=True,browser_private_journal_denied=True,
            sockets_cleaned=True,network_isolated=True,models_started=0,production_changed=False)))
    finally:
        if process.poll() is None:process.kill();process.wait()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--inside',action='store_true');parser.add_argument('--isolated-containers',action='store_true');args=parser.parse_args()
    if args.inside:inside();return
    if not args.isolated_containers:parser.error('explicit isolated fixture required')
    name='rras-operator-entry-'+uuid.uuid4().hex[:10]
    command=['docker','run','--rm','--name',name,'--pull=never','--network','none','--read-only','--cap-drop','ALL',
        '--cap-add','SETUID','--cap-add','SETGID','--cap-add','CHOWN','--cap-add','KILL','--cap-add','DAC_OVERRIDE',
        '--security-opt','no-new-privileges:true','--tmpfs','/tmp:rw,nosuid,nodev,size=64m,mode=1777',
        '--mount','type=bind,source='+str(ROOT)+',target=/fixture/engineering,readonly',
        '--mount','type=bind,source=/usr/bin/setfacl,target=/usr/bin/setfacl,readonly',
        '--user','0:0','--entrypoint','/usr/bin/env',IMAGE,'-i','PATH=/usr/bin:/bin','HOME=/nonexistent','LANG=C.UTF-8',
        '/opt/hermes/.venv/bin/python','-I','-B','/fixture/engineering/tools/rras_reporting/probe_operator_entry_host.py','--inside']
    try:
        result=subprocess.run(command,capture_output=True,text=True,timeout=70)
        if result.returncode:raise ValueError('offline operator entry fixture failed: '+result.stderr[-3000:])
        print(result.stdout.strip())
    finally:subprocess.run(['docker','rm','-f',name],capture_output=True,timeout=15)


if __name__=='__main__':main()
