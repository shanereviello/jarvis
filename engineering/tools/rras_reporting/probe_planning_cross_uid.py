"""Offline planning MCP to private history across distinct numeric UIDs."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import threading
import uuid
from contextlib import contextmanager

ROOT=Path(__file__).resolve().parents[2]
IMAGE='sha256:b99f4564d5e17ec0183314c0d2f6f633657cff4916fad0f05f6e7667722da432'
BASE=Path('/tmp/rras-planning-cross');ADAPTER=61180;NATIVE=61181;ROGUE=61182
SOCKET=BASE/'native.sock';BROKER=BASE/'broker'/'planning.sock'
uid=lambda n:f'00000000-0000-4000-8000-{n:012d}'


def local(name):
    spec=importlib.util.spec_from_file_location('planning_cross_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def history(name):
    path=Path(__file__).resolve().parent.parent/'rras_history'/(name+'.py')
    spec=importlib.util.spec_from_file_location('planning_cross_history_'+name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def drop(user):
    os.setgroups([]);os.setgid(NATIVE);os.setuid(user)


def parent():
    scope=dict(kind='repository',id='jarvis');storage=BASE/'private'/'history';storage.mkdir(mode=0o700)
    store=history('store').Store(storage,create=True)
    for name,cls in [('projects','Projects'),('scopes','Scopes'),('reporting','Reporting'),('evidence','Evidence'),
                     ('onboarding_reservations','Reservations')]:
        migration=getattr(history(name),cls)(store);migration.migrate(migration.migration_plan()['expected_sha256'])
    policy=dict(contract='engineering-history-access.v3',principals=[dict(uid=ADAPTER,private_read=['jarvis'],write=[],
        category_read=[],category_write=[],planning_agent='codex',planning_organization_id=uid(2),planning_teams=[uid(3)],
        planning_repositories=['jarvis'],planning_categories=[])])
    access=history('access').Access(store,policy);rpc=lambda message:access.dispatch(ADAPTER,message)
    adapter=local('onboarding_history').HistoryAdapter(rpc,
        lambda org,project:rpc(dict(method='planning_binding',organization_id=org,linear_project_id=project)),
        lambda org,linear,team,project,selected:rpc(dict(method='planning_reserve',organization_id=org,
            linear_project_id=linear,team_id=team,project_id=project,scope=selected)),[scope])
    origin=dict(organization_id=uid(2),team_id=uid(3),project_id=uid(4),project_identifier='P-ENG-1',
        project_url='https://linear.app/fixture/project/example',scope=scope,source_session=uid(5),source_actor=uid(6),agent='codex')
    issue=dict(organization_id=uid(2),team_id=uid(3),project_id=uid(4),id=uid(7),identifier='ENG-1',url='https://linear.app/fixture/issue/ENG-1')
    def lookup(peer,dispatch):
        if (peer,dispatch)!=(NATIVE,uid(1)):raise ValueError('fixture dispatch refused')
        return origin
    def issue_read(dispatch,selected,issue_id):
        if dispatch!=uid(1) or selected!=origin or issue_id!=issue['id']:raise ValueError('fixture issue refused')
        return issue
    grants={NATIVE:dict(agent='codex',organization_id=uid(2),team_id=uid(3),scopes=[scope])}
    @contextmanager
    def journal_connection():
        db=sqlite3.connect(BASE/'private'/'issue-journal.sqlite3')
        try:yield db
        finally:db.close()
    journal=local('onboarding_issue_journal').IssueJournal(journal_connection)
    with journal_connection() as db:journal.initialize(db)
    calls=[]
    def issue_create(dispatch,selected,plan,proposal):
        if dispatch!=uid(1) or selected!=origin or plan!='PLAN-01':raise ValueError('fixture issue creation refused')
        calls.append(proposal);return issue['id']
    broker=local('onboarding_broker').Broker(grants,lookup,issue_read,adapter,issue_journal=journal,issue_create=issue_create)
    transport=local('onboarding_broker_unix');stop=threading.Event();client=None
    with transport.server(BROKER,broker) as server:
        def serve():
            while not stop.is_set():server.serve_once()
        worker=threading.Thread(target=serve);worker.start();print('ready',flush=True)
        try:
            runtime=local('codex_runtime');client=runtime.SocketAppServer(SOCKET,0,timeout=30)
            launch=local('onboarding_mcp').Launch(BROKER,ADAPTER,sys.executable,allow_create=True)
            params=launch.parameters(uid(1));params.update(cwd=str(BASE/'workspace'),sandbox='read-only',approvalPolicy='never',ephemeral=True)
            params['config'].update({'analytics.enabled':False,'check_for_update_on_startup':False})
            thread=client.call('thread/start',params)['thread']['id'];launch.verify_inventory(client,thread)
            proposal=dict(name='Fixture',overview='Fixture',intended_outcome='Fixture',in_scope='Fixture',out_of_scope='Fixture',
                          markdown='# PLAN-01',plan_ids=['PLAN-01'])
            result=client.call('mcpServer/tool/call',dict(threadId=thread,server='engineering_planning',
                tool='engineering_draft_project',arguments=dict(proposal=proposal)))
            if result.get('isError'):raise ValueError('cross-UID draft refused')
            result=json.loads(result['content'][0]['text'])
            if result['execution_authorized'] is not False or adapter.project(scope,result['project_id'])['governing_version'] is not None:
                raise ValueError('draft authority differs')
            proposal=dict(plan_id='PLAN-01',title='Fixture',objective='Verify',rationale='Fixture',allowed_paths=['engineering'],
                          acceptance_criteria=[dict(id='AC-01',description='Verify')])
            result=client.call('mcpServer/tool/call',dict(threadId=thread,server='engineering_planning',
                tool='engineering_draft_issue',arguments=dict(proposal=proposal)))
            if result.get('isError'):raise ValueError('cross-UID draft work refused')
            result=json.loads(result['content'][0]['text'])
            if len(calls)!=1 or adapter.issue_binding(origin,issue['id'])['work_id']!=result['work_id']:raise ValueError('work mapping differs')
            print('recorded',flush=True)
            if sys.stdin.readline().strip()!='stop':raise ValueError('fixture coordination failed')
        finally:
            if client is not None:client.close()
            stop.set();worker.join(5)


def native_check(rogue):
    for path in (BASE/'private'/'history'/'history.sqlite3',BASE/'private'/'issue-journal.sqlite3'):
        try:path.read_bytes()
        except PermissionError:pass
        else:raise ValueError('native identity read private history')
    if rogue:
        try:local('onboarding_broker_unix').unix().call(BROKER,ADAPTER,dict(operation='draft.project',dispatch_id=uid(1),proposal={}))
        except (OSError,ValueError):return
        raise ValueError('wrong peer reached planning broker')


def inside():
    if not Path('/.dockerenv').exists() or os.getuid()!=0:raise ValueError('isolated privileged fixture required')
    if {line.split(':',1)[0].strip() for line in Path('/proc/self/net/dev').read_text().splitlines() if ':' in line}!={'lo'}:
        raise ValueError('network-isolated fixture required')
    BASE.mkdir(mode=0o755)
    for name,owner,mode in [('private',ADAPTER,0o700),('broker',ADAPTER,0o710),('workspace',NATIVE,0o700),('native',NATIVE,0o700)]:
        path=BASE/name;path.mkdir(mode=mode)
        if name=='native':
            home=path/'codex';home.mkdir(mode=0o700);os.chown(home,NATIVE,NATIVE)
        os.chown(path,owner,NATIVE)
    listener=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);listener.bind(str(SOCKET));SOCKET.chmod(0o600);os.chown(SOCKET,ADAPTER,NATIVE);listener.listen(1);listener.settimeout(15)
    adapter=subprocess.Popen([sys.executable,'-I','-B',__file__,'--role','parent'],preexec_fn=lambda:drop(ADAPTER),
        env=dict(PATH='/usr/bin:/bin',HOME='/nonexistent',LANG='C.UTF-8'),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    native=None
    try:
        if adapter.stdout.readline().strip()!='ready':raise ValueError('planning broker did not start: '+adapter.stderr.read()[-2000:])
        with listener.accept()[0] as connection:
            def native_user():drop(NATIVE);os.chdir(BASE/'workspace')
            native=subprocess.Popen(['/usr/local/bin/shrr-native-codex','app-server'],stdin=connection,stdout=connection,stderr=subprocess.DEVNULL,
                preexec_fn=native_user,env=dict(PATH='/usr/bin:/bin',HOME=str(BASE/'native'),CODEX_HOME=str(home),LANG='C.UTF-8'))
        if adapter.stdout.readline().strip()!='recorded':raise ValueError('native planning callback failed: '+adapter.stderr.read()[-2500:])
        for role,user in [('worker',NATIVE),('rogue',ROGUE)]:
            proc=subprocess.run([sys.executable,'-I','-B',__file__,'--role',role],preexec_fn=lambda:drop(user),
                env=dict(PATH='/usr/bin:/bin',HOME='/nonexistent',LANG='C.UTF-8'),capture_output=True,text=True,timeout=15)
            if proc.returncode:raise ValueError('planning identity check failed: '+proc.stderr[-2000:])
        adapter.stdin.write('stop\n');adapter.stdin.flush();_,stderr=adapter.communicate(timeout=15)
        if adapter.returncode:raise ValueError('planning adapter failed: '+stderr[-2000:])
        native.wait(timeout=10)
        print(json.dumps(dict(actual_native_app_server=True,distinct_numeric_uids=True,draft_and_work_retained=True,synthetic_issue_create=True,
            wrong_peer_denied=True,private_history_denied=True,network_isolated=True,models_started=0,turn_start_calls=0)))
    finally:
        listener.close()
        if adapter.poll() is None:adapter.kill();adapter.wait()
        if native is not None and native.poll() is None:native.kill();native.wait()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--role',choices=('inside','parent','worker','rogue'))
    parser.add_argument('--isolated-containers',action='store_true');parser.add_argument('--binary');args=parser.parse_args()
    if args.role=='inside':inside();return
    if args.role=='parent':parent();return
    if args.role in ('worker','rogue'):native_check(args.role=='rogue');return
    if not args.isolated_containers or not args.binary:parser.error('explicit isolated probe and binary required')
    binary=Path(args.binary)
    if not binary.is_absolute() or binary.resolve()!=binary or not binary.is_file():raise ValueError('exact native binary required')
    name='rras-planning-cross-'+uuid.uuid4().hex[:10]
    command=['docker','run','--rm','--name',name,'--pull=never','--network','none','--read-only','--cap-drop','ALL',
        '--cap-add','SETUID','--cap-add','SETGID','--cap-add','CHOWN','--security-opt','no-new-privileges:true',
        '--tmpfs','/tmp:rw,nosuid,nodev,size=128m,mode=1777','--mount','type=bind,source='+str(ROOT)+',target=/fixture/engineering,readonly',
        '--mount','type=bind,source='+str(binary)+',target=/usr/local/bin/shrr-native-codex,readonly',
        '--user','0:0','--entrypoint','/usr/bin/env',IMAGE,'-i','PATH=/usr/bin:/bin','HOME=/nonexistent','LANG=C.UTF-8',
        '/opt/hermes/.venv/bin/python','-I','-B','/fixture/engineering/tools/rras_reporting/probe_planning_cross_uid.py','--role','inside']
    try:
        result=subprocess.run(command,capture_output=True,text=True,timeout=80)
        if result.returncode:raise ValueError('offline planning isolation fixture failed: '+result.stderr[-3000:])
        print(result.stdout.strip())
    finally:subprocess.run(['docker','rm','-f',name],capture_output=True,timeout=15)


if __name__=='__main__':main()
