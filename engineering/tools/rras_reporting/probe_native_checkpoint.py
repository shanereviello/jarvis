"""Native App Server/MCP discovery without a turn, credentials or connectivity."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[3]
IMAGE='sha256:b99f4564d5e17ec0183314c0d2f6f633657cff4916fad0f05f6e7667722da432'


def local(name):
    spec=importlib.util.spec_from_file_location('native_checkpoint_probe_'+name,Path(__file__).with_name(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def inside():
    assert Path('/.dockerenv').exists() and os.getuid()==61159
    assert {line.split(':',1)[0].strip() for line in Path('/proc/self/net/dev').read_text().splitlines() if ':' in line}=={'lo'}
    base=Path('/tmp/native-checkpoint');base.mkdir(mode=0o700);state=base/'state'
    workspace=base/'workspace';workspace.mkdir(mode=0o700)
    intake=local('capture_intake');spool=intake.Spool(base/'spool',create=True)
    uid=lambda number:str(uuid.UUID(int=number))
    ctx=dict(project_id='prj_'+'1'*32,architecture=dict(document_id='doc_'+'2'*32,version=4,markdown_sha256='3'*64),
        work=dict(work_item_id='wrk_'+'4'*32,work_revision_sha256='5'*64,assignment_sha256='6'*64))
    config=dict(contract='codex-runtime-reporting.v1',spool=str(spool.root),scope=dict(kind='repository',id='jarvis'),
        contexts={uid(3):ctx},host_identity='offline-synthetic-container',oauth_client_id=None,capture=None)
    runtime=local('codex_runtime')
    policy=dict(contract='codex-runtime-policy.v1',organization_id=uid(1),app_user_id=uid(2),execution_authorized=False,
        execution_authority_reference='Offline discovery only; no turn is authorized',binary='/usr/local/bin/shrr-native-codex',
        cwd=str(workspace),sandbox='read-only',issues={uid(3):dict(project_id=ctx['project_id'],work_id=ctx['work']['work_item_id'],
            work_revision_sha256=ctx['work']['work_revision_sha256'],architecture_version=4,architecture_sha256='3'*64,plan_id='SHRR-03')})
    journal=runtime.Runtime(state,policy,create=True);journal.close()
    home=state/'codex-home';home.mkdir(mode=0o700)
    configuration=base/'reporting.json';configuration.write_text(json.dumps(config));configuration.chmod(0o600)
    tool=local('runtime_checkpoint_mcp').Launch(state,configuration,sys.executable)
    client=runtime.AppServer('/usr/local/bin/shrr-native-codex',workspace,codex_home=home,timeout=30)
    try:
        params=tool.parameters(uid(5));params.update(cwd=str(workspace),sandbox='read-only',approvalPolicy='on-request',ephemeral=True)
        params['config'].update({'analytics.enabled':False,'check_for_update_on_startup':False})
        response=client.call('thread/start',params);thread=response['thread']['id']
        found=False;inventory=[]
        for _ in range(10):
            found=tool.verify_inventory(client,thread)
            if found:break
            time.sleep(0.3)
        if not found:
            inventory=client.call('mcpServerStatus/list',dict(threadId=thread,detail='toolsAndAuthOnly',limit=100))
            raise ValueError('Scoped inventory unavailable: '+json.dumps(inventory))
        print(json.dumps(dict(native_version=subprocess.check_output(['/usr/local/bin/shrr-native-codex','--version'],text=True).strip(),
            binary_sha256=hashlib.sha256(Path('/usr/local/bin/shrr-native-codex').read_bytes()).hexdigest(),
            thread_created=True,scoped_mcp_discovered=True,models_started=0,turn_start_calls=0,
            real_credentials=False,network_interfaces=['lo'],production_mounts=False)))
    finally:client.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--inside',action='store_true')
    parser.add_argument('--isolated-containers',action='store_true');parser.add_argument('--binary');args=parser.parse_args()
    if args.inside:inside();return
    if not args.isolated_containers or not args.binary:parser.error('explicit offline fixture and reviewed binary required')
    binary=Path(args.binary)
    if not binary.is_absolute() or binary.resolve()!=binary or not binary.is_file():raise ValueError('exact installed native binary required')
    name='rras-native-checkpoint-'+uuid.uuid4().hex[:10]
    command=['docker','run','--rm','--name',name,'--pull=never','--network','none','--read-only','--cap-drop','ALL',
        '--security-opt','no-new-privileges:true','--tmpfs','/tmp:rw,nosuid,nodev,size=128m,mode=1777',
        '--mount','type=bind,source='+str(ROOT/'engineering')+',target=/fixture/engineering,readonly',
        '--mount','type=bind,source='+str(binary)+',target=/usr/local/bin/shrr-native-codex,readonly',
        '--user','61159:61159','--entrypoint','/usr/bin/env',IMAGE,'-i','PATH=/usr/bin:/bin','HOME=/nonexistent','LANG=C.UTF-8',
        '/opt/hermes/.venv/bin/python','-I','-B','/fixture/engineering/tools/rras_reporting/probe_native_checkpoint.py','--inside']
    try:
        result=subprocess.run(command,capture_output=True,text=True,timeout=75)
        if result.returncode:raise ValueError('Offline native checkpoint fixture failed: '+result.stderr[-2500:])
        print(result.stdout.strip())
    finally:subprocess.run(['docker','rm','-f',name],capture_output=True,timeout=15)


if __name__=='__main__':main()
