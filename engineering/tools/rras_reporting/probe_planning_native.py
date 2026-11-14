"""Opt-in, offline actual Codex App Server and planning MCP fixture."""
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


def local(name):
    spec=importlib.util.spec_from_file_location('planning_native_probe_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def history(name):
    path=Path(__file__).resolve().parent.parent/'rras_history'/(name+'.py')
    spec=importlib.util.spec_from_file_location('planning_native_history_'+name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def inside():
    if not Path('/.dockerenv').exists():raise ValueError('isolated container required')
    devices={line.split(':',1)[0].strip() for line in Path('/proc/self/net/dev').read_text().splitlines() if ':' in line}
    if devices!={'lo'}:raise ValueError('network-isolated fixture required')
    root=Path('/tmp/planning-native');root.mkdir(mode=0o700)
    workspace=root/'workspace';workspace.mkdir(mode=0o700)
    home=root/'home';home.mkdir(mode=0o700)
    uid=lambda n:f'00000000-0000-4000-8000-{n:012d}'
    dispatch=uid(1);scope=dict(kind='repository',id='jarvis');peer=os.getuid()
    storage=root/'history';storage.mkdir(mode=0o700)
    store=history('store').Store(storage,create=True)
    for name,cls in [('projects','Projects'),('scopes','Scopes'),('reporting','Reporting'),('evidence','Evidence'),
                     ('onboarding_reservations','Reservations')]:
        migration=getattr(history(name),cls)(store);migration.migrate(migration.migration_plan()['expected_sha256'])
    policy=dict(contract='engineering-history-access.v3',principals=[dict(uid=peer,private_read=['jarvis'],write=[],
        category_read=[],category_write=[],planning_agent='codex',planning_organization_id=uid(2),planning_teams=[uid(3)],
        planning_repositories=['jarvis'],planning_categories=[])])
    access=history('access').Access(store,policy);rpc=lambda message:access.dispatch(peer,message)
    adapter=local('onboarding_history').HistoryAdapter(rpc,
        lambda org,project:rpc(dict(method='planning_binding',organization_id=org,linear_project_id=project)),
        lambda org,linear,team,project,selected:rpc(dict(method='planning_reserve',organization_id=org,
            linear_project_id=linear,team_id=team,project_id=project,scope=selected)),[scope])
    origin=dict(organization_id=uid(2),team_id=uid(3),project_id=uid(4),project_identifier='P-ENG-1',
        project_url='https://linear.app/fixture/project/example',scope=scope,source_session=uid(5),source_actor=uid(6),agent='codex')
    grants={peer:dict(agent='codex',organization_id=uid(2),team_id=uid(3),scopes=[scope])}
    def lookup(caller,selected):
        if caller!=peer or selected!=dispatch:raise ValueError('fixture session refused')
        return origin
    issue=dict(organization_id=uid(2),team_id=uid(3),project_id=uid(4),id=uid(7),identifier='ENG-1',
               url='https://linear.app/fixture/issue/ENG-1')
    def issue_read(selected_dispatch,selected,issue_id):
        if selected_dispatch!=dispatch or selected!=origin or issue_id!=issue['id']:raise ValueError('fixture issue refused')
        return issue
    broker=local('onboarding_broker').Broker(grants,lookup,issue_read,adapter)
    stop=threading.Event();transport=local('onboarding_broker_unix');client=None
    with transport.server(root/'broker.sock',broker) as server:
        def serve():
            while not stop.is_set():server.serve_once()
        worker=threading.Thread(target=serve);worker.start()
        try:
            runtime=local('codex_runtime')
            client=runtime.AppServer('/usr/local/bin/shrr-native-codex',str(workspace),timeout=30,codex_home=home)
            launch=local('onboarding_mcp').Launch(root/'broker.sock',os.getuid(),sys.executable)
            params=launch.parameters(dispatch);params.update(cwd=str(workspace),sandbox='read-only',approvalPolicy='never',ephemeral=True)
            params['config'].update({'analytics.enabled':False,'check_for_update_on_startup':False})
            thread=client.call('thread/start',params)['thread']['id']
            launch.verify_inventory(client,thread)
            proposal=dict(name='Fixture',overview='Fixture',intended_outcome='Fixture',in_scope='Fixture',
                out_of_scope='Fixture',markdown='# PLAN-01',plan_ids=['PLAN-01'])
            result=client.call('mcpServer/tool/call',dict(threadId=thread,server='engineering_planning',
                tool='engineering_draft_project',arguments=dict(proposal=proposal)))
            if result.get('isError'):raise ValueError('native planning MCP call refused')
            received=json.loads(result['content'][0]['text'])
            project=adapter.project(scope,received['project_id'])
            if received.get('execution_authorized') is not False or project['governing_version'] is not None:
                raise ValueError('draft or authority differs')
            work=dict(plan_id='PLAN-01',title='Fixture',objective='Verify',rationale='Fixture',allowed_paths=['engineering'],
                acceptance_criteria=[dict(id='AC-01',description='Verify')])
            result=client.call('mcpServer/tool/call',dict(threadId=thread,server='engineering_planning',
                tool='engineering_draft_work',arguments=dict(issue_id=issue['id'],proposal=work)))
            if result.get('isError'):raise ValueError('native planning work call refused')
            mapped=json.loads(result['content'][0]['text'])
            if mapped.get('execution_authorized') is not False or adapter.issue_binding(origin,issue['id'])['work_id']!=mapped['work_id']:
                raise ValueError('draft work mapping differs')
            print(json.dumps(dict(actual_native_app_server=True,planning_mcp_call=True,readonly_sandbox=True,
                retained_fixture_draft=True,retained_fixture_work_mapping=True,governing_architecture=False,network_isolated=True,
                models_started=0,turn_start_calls=0,real_credentials=False)))
        finally:
            if client is not None:client.close()
            stop.set();worker.join(5)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--inside',action='store_true')
    parser.add_argument('--isolated-containers',action='store_true');parser.add_argument('--binary');args=parser.parse_args()
    if args.inside:inside();return
    if not args.isolated_containers or not args.binary:parser.error('explicit isolated probe and binary required')
    binary=Path(args.binary)
    if not binary.is_absolute() or binary.resolve()!=binary or not binary.is_file():raise ValueError('exact native binary required')
    name='rras-planning-native-'+uuid.uuid4().hex[:10]
    command=['docker','run','--rm','--name',name,'--pull=never','--network','none','--read-only','--cap-drop','ALL',
        '--security-opt','no-new-privileges:true','--tmpfs','/tmp:rw,nosuid,nodev,size=128m,mode=1777',
        '--mount','type=bind,source='+str(ROOT)+',target=/fixture/engineering,readonly',
        '--mount','type=bind,source='+str(binary)+',target=/usr/local/bin/shrr-native-codex,readonly',
        '--user','61180:61180','--entrypoint','/usr/bin/env',IMAGE,'-i','PATH=/usr/bin:/bin','HOME=/nonexistent',
        'LANG=C.UTF-8','/opt/hermes/.venv/bin/python','-I','-B','/fixture/engineering/tools/rras_reporting/probe_planning_native.py','--inside']
    try:
        result=subprocess.run(command,capture_output=True,text=True,timeout=70)
        if result.returncode:raise ValueError('offline native planning fixture failed: '+result.stderr[-3000:])
        print(result.stdout.strip())
    finally:subprocess.run(['docker','rm','-f',name],capture_output=True,timeout=15)


if __name__=='__main__':main()
