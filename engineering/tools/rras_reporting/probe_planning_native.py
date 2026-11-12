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


def inside():
    if not Path('/.dockerenv').exists():raise ValueError('isolated container required')
    devices={line.split(':',1)[0].strip() for line in Path('/proc/self/net/dev').read_text().splitlines() if ':' in line}
    if devices!={'lo'}:raise ValueError('network-isolated fixture required')
    root=Path('/tmp/planning-native');root.mkdir(mode=0o700)
    workspace=root/'workspace';workspace.mkdir(mode=0o700)
    home=root/'home';home.mkdir(mode=0o700)
    dispatch='00000000-0000-4000-8000-000000000001';observed=[]
    class Broker:
        grants={os.getuid():{}}
        def dispatch(self,peer,message):
            if peer!=os.getuid() or message.get('operation')!='draft.project' or message.get('dispatch_id')!=dispatch:
                raise ValueError('fixture request refused')
            observed.append(message)
            return dict(designation='draft',execution_authorized=False)
    stop=threading.Event();transport=local('onboarding_broker_unix');client=None
    with transport.server(root/'broker.sock',Broker()) as broker:
        def serve():
            while not stop.is_set():broker.serve_once()
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
            if result.get('isError') or not observed:raise ValueError('native planning MCP call refused')
            print(json.dumps(dict(actual_native_app_server=True,planning_mcp_call=True,readonly_sandbox=True,
                network_isolated=True,models_started=0,turn_start_calls=0,real_credentials=False)))
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
