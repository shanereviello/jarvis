"""Offline native App Server/recording acceptance across real numeric Unix UIDs."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import uuid

ROOT=Path(__file__).resolve().parents[3]
IMAGE='sha256:b99f4564d5e17ec0183314c0d2f6f633657cff4916fad0f05f6e7667722da432'
BASE=Path('/tmp/shrr-native-isolation');ADAPTER=61180;NATIVE=61181;ROGUE=61182
SOCKET=BASE/'native.sock';REPORT=BASE/'report/checkpoint.sock'
uid=lambda number:str(uuid.UUID(int=number))


def local(name):
    spec=importlib.util.spec_from_file_location('native_isolation_'+name,Path(__file__).with_name(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def identity(user):
    os.setgroups([]);os.setgid(NATIVE);os.setuid(user)


def child(role,user):
    return subprocess.Popen([sys.executable,'-I','-B',__file__,'--role',role],preexec_fn=lambda:identity(user),
        env=dict(PATH='/usr/bin:/bin',HOME='/nonexistent',LANG='C.UTF-8'),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)


def parent():
    m=local('codex_runtime');intake=local('capture_intake');root=BASE/'private'
    bridge=root/'bridge-token';bridge.write_text('SYNTHETIC-PRIVATE-N8N-BRIDGE-MARKER');bridge.chmod(0o600)
    ctx=dict(project_id='prj_'+'1'*32,architecture=dict(document_id='doc_'+'2'*32,version=4,markdown_sha256='3'*64),
        work=dict(work_item_id='wrk_'+'4'*32,work_revision_sha256='5'*64,assignment_sha256='6'*64))
    pin=dict(project_id=ctx['project_id'],work_id=ctx['work']['work_item_id'],work_revision_sha256=ctx['work']['work_revision_sha256'],
        architecture_version=4,architecture_sha256='3'*64,plan_id='SHRR-03')
    policy=dict(contract='codex-runtime-policy.v1',organization_id=uid(1),app_user_id=uid(2),execution_authorized=True,
        execution_authority_reference='Synthetic admitted journal context only; no native turn is called',
        binary='/usr/local/bin/shrr-native-codex',cwd=str(BASE/'workspace'),sandbox='read-only',issues={uid(3):pin})
    spool=intake.Spool(root/'spool',create=True)
    configuration=dict(contract='codex-runtime-reporting.v1',spool=str(spool.root),scope=dict(kind='repository',id='jarvis'),
        contexts={uid(3):ctx},host_identity='offline-cross-uid-fixture',oauth_client_id=None,capture=None)
    reporter=local('runtime_reporting').Reporter(configuration,policy);runtime=m.Runtime(root/'runtime',policy,create=True,reporter=reporter)
    request=dict(contract='codex-dispatch.v1',dispatch_id=uid(4),organization_id=uid(1),app_user_id=uid(2),
        session_id=uid(5),issue_id=uid(3),message='Synthetic recording context; no model turn.',binding=pin)
    raw=m.encoded(runtime.validate(request))
    with runtime.connection() as db:
        db.execute('INSERT INTO sessions(session,issue) VALUES(?,?)',(uid(5),uid(3)))
        db.execute('INSERT INTO turns(dispatch,session,issue,request,digest,state) VALUES(?,?,?,?,?,?)',
            (uid(4),uid(5),uid(3),raw,m.hashlib.sha256(raw).hexdigest(),'preparing'))
    runtime._report(uid(4));stopped=threading.Event();broker_module=local('runtime_checkpoint_broker');client=None
    # The fixture uses one ordinary primary group for path traversal. Production
    # uses the existing exact named-UID ACL helper and no shared group grant.
    with broker_module.Server(REPORT,runtime,configuration,NATIVE,on_bound=lambda path:os.chmod(path.parent,0o710)) as broker:
        def serve():
            while not stopped.is_set():broker.serve_once()
        worker=threading.Thread(target=serve,daemon=True);worker.start();print('ready',flush=True)
        try:
            client=m.SocketAppServer(SOCKET,0,timeout=30)
            launch=local('runtime_checkpoint_mcp').BrokerLaunch(REPORT,ADAPTER,sys.executable)
            params=launch.parameters(uid(5),uid(4));params.update(cwd=policy['cwd'],sandbox='read-only',approvalPolicy='on-request',ephemeral=True)
            params['config'].update({'analytics.enabled':False,'check_for_update_on_startup':False})
            native=client.call('thread/start',params)['thread'];thread=native['id']
            for _ in range(10):
                if launch.verify_inventory(client,thread):break
                time.sleep(.2)
            else:raise ValueError('native scoped recorder was not discovered')
            with runtime.connection() as db:
                db.execute("UPDATE turns SET thread=?,turn='synthetic-no-model-turn',state='running' WHERE dispatch=?",(thread,uid(4)))
            result=client.call('mcpServer/tool/call',dict(threadId=thread,server='engineering_checkpoint',tool='engineering_checkpoint',
                arguments=dict(key='cross-uid-native-sdk',observations=['Actual native MCP callback reached the bound private adapter.'],next_step='Keep real model acceptance separate.')))
            assert not result.get('isError') and json.loads(result['content'][0]['text'])['work_item_id']==pin['work_id']
            print('recorded',flush=True)
            assert sys.stdin.readline().strip()=='stop'
            with spool.connection() as db:
                saved=[spool.c.decode(x[0]) for x in db.execute('SELECT request FROM items')]
            assert any(x['operation']=='checkpoint.report' and 'Actual native MCP callback' in str(x['body']) for x in saved)
        finally:
            if client:client.close()
            stopped.set();worker.join(timeout=3);runtime.close()


def probe_worker(rogue=False):
    broker=local('runtime_checkpoint_mcp').BrokerClient(REPORT,ADAPTER,uid(5),uid(4))
    if rogue:
        try:broker.record(dict(key='rogue',observations=['Must be refused.'],next_step='None.'))
        except (ValueError,OSError):return
        raise ValueError('wrong UID reached the recorder')
    for path in (BASE/'private/bridge-token',BASE/'private/runtime/runtime.sqlite3',BASE/'private/spool/spool.sqlite3'):
        try:path.read_bytes()
        except PermissionError:pass
        else:raise ValueError('native account read private adapter material')
    u=local('codex_runtime').history_unix()
    for message in (dict(method='project_read'),dict(method='checkpoint',session_id=uid(99),dispatch_id=uid(4),
            arguments=dict(key='wrong-session',observations=['Refuse.'],next_step='None.')),
            dict(method='checkpoint',session_id=uid(5),dispatch_id=uid(99),arguments=dict(key='stale',observations=['Refuse.'],next_step='None.'))):
        try:u.call(REPORT,ADAPTER,message)
        except ValueError:pass
        else:raise ValueError('unscoped or stale native recording accepted')


def inside():
    assert Path('/.dockerenv').exists() and os.getuid()==0
    assert {line.split(':',1)[0].strip() for line in Path('/proc/self/net/dev').read_text().splitlines() if ':' in line}=={'lo'}
    BASE.mkdir(mode=0o755)
    for name,owner in [('private',ADAPTER),('report',ADAPTER),('workspace',NATIVE),('native',NATIVE)]:
        path=BASE/name;path.mkdir(mode=0o700)
        if name=='native':
            home=path/'codex';home.mkdir(mode=0o700);os.chown(home,NATIVE,NATIVE)
        os.chown(path,owner,NATIVE)
    home=BASE/'native/codex'
    listener=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);listener.bind(str(SOCKET));SOCKET.chmod(0o600);os.chown(SOCKET,ADAPTER,NATIVE);listener.listen(1);listener.settimeout(15)
    adapter=child('parent',ADAPTER);native=None
    try:
        assert adapter.stdout.readline().strip()=='ready'
        with listener.accept()[0] as connection:
            def native_identity():identity(NATIVE);os.chdir(BASE/'workspace')
            native=subprocess.Popen(['/usr/local/bin/shrr-native-codex','app-server'],stdin=connection,stdout=connection,stderr=subprocess.DEVNULL,
                preexec_fn=native_identity,env=dict(PATH='/usr/bin:/bin',HOME=str(BASE/'native'),CODEX_HOME=str(home),LANG='C.UTF-8'))
        line=adapter.stdout.readline().strip()
        if line!='recorded':raise ValueError('native callback failed: '+adapter.stderr.read()[-2000:])
        for role,user in [('worker',NATIVE),('rogue',ROGUE)]:
            proc=child(role,user);stdout,stderr=proc.communicate(timeout=15)
            if proc.returncode:raise ValueError(role+' boundary failed: '+stderr[-2000:])
        adapter.stdin.write('stop\n');adapter.stdin.flush();stdout,stderr=adapter.communicate(timeout=10)
        if adapter.returncode:raise ValueError('private adapter fixture failed: '+stderr[-2000:])
        native.wait(timeout=10)
        print(json.dumps(dict(native_app_server=True,stdio_over_unix_socket=True,distinct_numeric_uids=True,
            actual_native_mcp_callback=True,private_bridge_file_denied=True,private_runtime_and_spool_denied=True,
            history_method_denied=True,wrong_uid_denied=True,stale_dispatch_denied=True,exact_bound_work=True,
            fixture_acl='ordinary_primary_group_for_traversal;production_named_UID_ACL_pending_host_acceptance',
            models_started=0,turn_start_calls=0,real_credentials=False,production_mounts=False,permanent_accounts_created=False)))
    finally:listener.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--role',choices=('inside','parent','worker','rogue'))
    parser.add_argument('--isolated-containers',action='store_true');parser.add_argument('--binary');args=parser.parse_args()
    if args.role=='inside':inside();return
    if args.role=='parent':parent();return
    if args.role in ('worker','rogue'):probe_worker(args.role=='rogue');return
    if not args.isolated_containers or not args.binary:parser.error('explicit isolated probe and reviewed binary required')
    binary=Path(args.binary)
    if not binary.is_absolute() or binary.resolve()!=binary or not binary.is_file():raise ValueError('exact native binary required')
    name='rras-native-isolation-'+uuid.uuid4().hex[:10]
    argv=['docker','run','--rm','--name',name,'--pull=never','--network','none','--read-only','--cap-drop','ALL',
        '--cap-add','SETUID','--cap-add','SETGID','--cap-add','CHOWN','--security-opt','no-new-privileges:true',
        '--tmpfs','/tmp:rw,nosuid,nodev,size=128m,mode=1777','--mount','type=bind,source='+str(ROOT/'engineering')+',target=/fixture/engineering,readonly',
        '--mount','type=bind,source='+str(binary)+',target=/usr/local/bin/shrr-native-codex,readonly','--user','0:0','--entrypoint','/usr/bin/env',IMAGE,
        '-i','PATH=/usr/bin:/bin','HOME=/nonexistent','LANG=C.UTF-8','/opt/hermes/.venv/bin/python','-I','-B',
        '/fixture/engineering/tools/rras_reporting/probe_native_isolation.py','--role','inside']
    try:
        result=subprocess.run(argv,capture_output=True,text=True,timeout=85)
        if result.returncode:raise ValueError('offline native isolation fixture failed: '+result.stderr[-3000:])
        print(result.stdout.strip())
    finally:subprocess.run(['docker','rm','-f',name],capture_output=True,timeout=15)


if __name__=='__main__':main()
