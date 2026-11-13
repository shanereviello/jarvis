"""Exercise Jarvis planning registration in an offline disposable Hermes image."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

ROOT=Path(__file__).resolve().parents[2]
IMAGE='sha256:b99f4564d5e17ec0183314c0d2f6f633657cff4916fad0f05f6e7667722da432'


def inside():
    if not Path('/.dockerenv').exists() or os.getuid()!=0:raise ValueError('isolated root fixture required')
    if {line.split(':',1)[0].strip() for line in Path('/proc/self/net/dev').read_text().splitlines() if ':' in line}!={'lo'}:
        raise ValueError('network-isolated fixture required')
    config_dir=Path('/tmp/planning-probe');config_dir.mkdir(mode=0o755)
    config=config_dir/'config.json'
    config.write_text(json.dumps(dict(contract='hermes-planning-config.v1',origin='http://127.0.0.1:8768',
        token_file='/tmp/planning-probe/token',allow_create=True,allow_review=True)))
    config.chmod(0o640);os.chown(config,0,61186)
    os.setgroups([]);os.setgid(61186);os.setuid(61186)
    entry=Path('/fixture/engineering/tools/rras_reporting/hermes_planning.py')
    spec=importlib.util.spec_from_file_location('fixture_hermes_planning',entry)
    planning=importlib.util.module_from_spec(spec);spec.loader.exec_module(planning)
    class Context:
        def __init__(self):self.tools={}
        def register_tool(self,**tool):self.tools[tool['name']]=tool
    ctx=Context();planning.register_configured(ctx,config)
    expected={'engineering_draft_project','engineering_draft_work','engineering_draft_issue','engineering_prepare_review'}
    if set(ctx.tools)!=expected or any(tool['toolset']!='engineering_planning' for tool in ctx.tools.values()):
        raise ValueError('planning tool inventory differs')
    try:planning.local('hermes_native_context').actual()
    except ValueError as error:
        if 'not bound' not in str(error):raise
    else:raise ValueError('unbound native session was accepted')
    from gateway import session_context
    organization=str(uuid.UUID(int=1));session=str(uuid.UUID(int=2));alias='linear:'+organization+':'+session;run='run_'+'a'*32
    tokens=session_context.set_session_vars(platform='api_server',chat_id=alias,session_id='fixture-native',session_key=run)
    try:
        actual=planning.local('hermes_native_context').actual()
        if actual!=dict(organization_id=organization,session_id=session,hermes_session_id=alias,run_id=run):
            raise ValueError('bound native session differs')
    finally:session_context.clear_session_vars(tokens)
    print(json.dumps(dict(actual_hermes_import=True,tool_inventory_verified=True,unbound_native_denied=True,
        native_context_bound=True,separate_numeric_uid=True,network_isolated=True,models_started=0,production_changed=False),sort_keys=True))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--inside',action='store_true');parser.add_argument('--isolated-containers',action='store_true');args=parser.parse_args()
    if args.inside:inside();return
    if not args.isolated_containers:parser.error('explicit isolated fixture required')
    name='rras-hermes-planning-'+uuid.uuid4().hex[:10]
    command=['docker','run','--rm','--name',name,'--pull=never','--network','none','--read-only','--cap-drop','ALL',
        '--cap-add','SETUID','--cap-add','SETGID','--cap-add','CHOWN','--security-opt','no-new-privileges:true',
        '--tmpfs','/tmp:rw,nosuid,nodev,size=32m,mode=1777',
        '--mount','type=bind,source='+str(ROOT)+',target=/fixture/engineering,readonly',
        '--user','0:0','--entrypoint','/usr/bin/env',IMAGE,'-i','PATH=/usr/bin:/bin','HOME=/nonexistent','LANG=C.UTF-8',
        '/opt/hermes/.venv/bin/python','-B','/fixture/engineering/tools/rras_reporting/probe_hermes_planning_plugin.py','--inside']
    try:
        result=subprocess.run(command,capture_output=True,text=True,timeout=50)
        if result.returncode:raise ValueError('offline Hermes planning fixture failed: '+result.stderr[-3000:])
        print(result.stdout.strip())
    finally:subprocess.run(['docker','rm','-f',name],capture_output=True,timeout=15)


if __name__=='__main__':main()
