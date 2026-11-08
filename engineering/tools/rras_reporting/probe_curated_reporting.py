"""Actual stdio MCP / cross-UID Unix rehearsal in a disposable offline container."""
import argparse
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import uuid

IMAGE='sha256:b99f4564d5e17ec0183314c0d2f6f633657cff4916fad0f05f6e7667722da432'
ROOT=Path(__file__).resolve().parents[3]
BASE=Path('/tmp/shrr-curated-reporting');CATALOG=BASE/'private/catalog';SOCKET=BASE/'run/read.sock'
SERVICE=61157;READER=61158


def local(name):
    spec=importlib.util.spec_from_file_location('reporting_mcp_probe_'+name,ROOT/'engineering/tools/rras_history'/(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def policy(granted=True):return dict(contract='engineering-curated-read-access.v1',principals=[dict(uid=READER,repositories=['jarvis'] if granted else [])])


def seed():
    c=local('contract');ctx=dict(project_id='prj_'+'1'*32,
        architecture=dict(document_id='doc_'+'2'*32,version=4,markdown_sha256='3'*64),
        work=dict(work_item_id='wrk_'+'4'*32,work_revision_sha256='5'*64,assignment_sha256='6'*64))
    request=dict(contract='engineering-reporting.v1',operation='checkpoint.report',client_event_key='synthetic-mcp-profile',
        expected_head=None,scope=dict(kind='repository',id='jarvis'),context=ctx,
        source=dict(kind='agent_reported',namespace='fixture',id='synthetic'),occurred_at=None,
        body=dict(report_id='rpt_'+'7'*32,attempt_id=None,observations=['CURATED-ENGINEERING-RESULT'],
            alternatives_and_reasons=['PRIVATE-UNSELECTED-NARRATIVE'],changes=[],validation=[],open_questions=[],next_step='Verify retrieval',references=[]))
    request=local('reporting_contract').validate(request)
    receipt=dict(request_sha256=c.digest(c.encoded(request)),scope=request['scope'],context=ctx,visibility='operator_private',
        authority_granted=False,receipt_id='rcp_'+'8'*32,recorded_at='2026-11-07T12:00:00Z')
    profile=dict(contract='engineering-reporting-publication-profile.v1',profile_id='prf_'+'9'*32,version=1,
        projects=[dict(project_id=ctx['project_id'],repository_id='jarvis')],
        fields={'checkpoint.report':['observations','next_step']},authorization_reference='Synthetic profile only')
    local('curated_publication').initialize(CATALOG,['jarvis'])
    local('curated_reporting').publish_profile(CATALOG,[dict(submission=request,receipt=receipt)],profile,c.digest(c.encoded(profile)),None,approve_profile=True)


def serve(granted):
    stop=threading.Event()
    def control():sys.stdin.readline();stop.set()
    threading.Thread(target=control,daemon=True).start()
    with local('curated_read_unix').Server(SOCKET,CATALOG,policy(granted)) as server:
        print('ready',flush=True)
        while not stop.is_set():server.serve_once()


def is_error(value):return getattr(value,'is_error',getattr(value,'isError',False)) is True


async def client(role,context):
    from mcp import ClientSession,StdioServerParameters
    from mcp.client.stdio import stdio_client
    params=StdioServerParameters(command=sys.executable,args=['-I','-B',str(ROOT/'engineering/tools/rras_history/curated_mcp.py'),
        '--socket',str(SOCKET),'--service-uid',str(SERVICE),'--reader-uid',str(READER)],env=dict(PATH='/usr/bin:/bin',HOME='/nonexistent',LANG='C.UTF-8'))
    async with stdio_client(params) as (read,write):
        async with ClientSession(read,write) as session:
            await session.initialize();tools=await session.list_tools()
            assert {x.name for x in tools.tools}=={'engineering_history_search','engineering_history_read'}
            result=await session.call_tool('engineering_history_search',dict(repository_id='jarvis'))
            if role=='revoked':assert is_error(result);return dict(revoked=True)
            assert not is_error(result);page=json.loads(result.content[0].text)
            if role=='withdrawn':
                assert page['entries']==[]
                assert is_error(await session.call_tool('engineering_history_read',dict(repository_id='jarvis',**context)))
                assert is_error(await session.call_tool('engineering_history_search',dict(repository_id='jarvis',generation_sha256=context['generation_sha256'])))
                return dict(withdrawal_and_stale_generation_refused=True)
            assert len(page['entries'])==1 and 'CURATED-ENGINEERING-RESULT' in json.dumps(page)
            assert 'PRIVATE-UNSELECTED-NARRATIVE' not in json.dumps(page)
            entry=page['entries'][0];context=dict(entry_id=entry['entry_id'],generation_sha256=page['generation_sha256'])
            exact=await session.call_tool('engineering_history_read',dict(repository_id='jarvis',**context))
            assert not is_error(exact) and json.loads(exact.content[0].text)['entry']==entry
            assert entry['context']['architecture']['version']==4 and entry['source_authenticated'] is False
            assert is_error(await session.call_tool('engineering_history_search',dict(repository_id='other')))
            assert is_error(await session.call_tool('publish',{}))
            return context


def child(role,context=None,*,uid=SERVICE):
    def identity():os.setgroups([]);os.setgid(READER);os.setuid(uid)
    argv=[sys.executable,'-I','-B',__file__,'--role',role]
    if context:argv+=['--context',json.dumps(context)]
    return subprocess.run(argv,env=dict(PATH='/usr/bin:/bin',HOME='/nonexistent',LANG='C.UTF-8'),
        preexec_fn=identity,capture_output=True,text=True,timeout=30)


def inside():
    assert os.getuid()==0 and Path('/.dockerenv').exists() and ROOT==Path('/fixture')
    assert {line.split(':',1)[0].strip() for line in Path('/proc/self/net/dev').read_text().splitlines() if ':' in line}=={'lo'}
    assert not BASE.exists();BASE.mkdir(mode=0o755)
    for name,mode in [('private',0o700),('run',0o710)]:
        p=BASE/name;p.mkdir(mode=mode);os.chown(p,SERVICE,READER)
    os.setgroups([]);os.setgid(READER)
    result=child('seed');assert result.returncode==0,result.stderr[-2000:]
    def identity():os.setgroups([]);os.setgid(READER);os.setuid(SERVICE)
    def start(role):
        proc=subprocess.Popen([sys.executable,'-I','-B',__file__,'--role',role],preexec_fn=identity,
            env=dict(PATH='/usr/bin:/bin',HOME='/nonexistent',LANG='C.UTF-8'),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        assert proc.stdout.readline().strip()=='ready';return proc
    def stop(proc):
        proc.stdin.write('stop\n');proc.stdin.flush();proc.wait(timeout=5)
        assert proc.returncode==0 and not SOCKET.exists()
    server=start('server')
    try:
        result=child('read',uid=READER);assert result.returncode==0,result.stderr[-2000:];context=json.loads(result.stdout)
        result=child('withdraw',context);assert result.returncode==0,result.stderr[-2000:]
        result=child('withdrawn',context,uid=READER);assert result.returncode==0,result.stderr[-2000:]
    finally:stop(server)
    server=start('server-revoked')
    try:
        result=child('revoked',uid=READER);assert result.returncode==0,result.stderr[-2000:]
    finally:stop(server)
    print(json.dumps(dict(actual_stdio_mcp=True,cross_uid_unix=True,exact_structured_context=True,private_fields_excluded=True,
        repository_denial=True,action_tool_denial=True,withdrawal_stale_generation_denial=True,reader_revocation_denial=True,
        real_credentials=False,real_history=False,models_started=0,production_mounts=False)))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--isolated-containers',action='store_true')
    parser.add_argument('--role',choices=('inside','seed','server','server-revoked','read','withdraw','withdrawn','revoked'))
    parser.add_argument('--context');args=parser.parse_args()
    if args.isolated_containers:
        name='rras-curated-reporting-'+uuid.uuid4().hex[:10]
        command=['docker','run','--rm','--name',name,'--pull=never','--network','none','--read-only','--cap-drop','ALL',
            '--cap-add','SETUID','--cap-add','SETGID','--cap-add','CHOWN','--security-opt','no-new-privileges:true',
            '--tmpfs','/tmp:rw,nosuid,nodev,size=64m,mode=1777',
            '--mount','type=bind,source='+str(ROOT/'engineering')+',target=/fixture/engineering,readonly',
            '--user','0:0','--entrypoint','/usr/bin/env',IMAGE,'-i','PATH=/usr/bin:/bin','HOME=/nonexistent','LANG=C.UTF-8',
            '/opt/hermes/.venv/bin/python','-I','-B','/fixture/engineering/tools/rras_reporting/probe_curated_reporting.py','--role','inside']
        try:
            result=subprocess.run(command,capture_output=True,text=True,timeout=90)
            if result.returncode:raise ValueError('Synthetic MCP container failed: '+result.stderr[-2500:])
            print(result.stdout.strip())
        finally:subprocess.run(['docker','rm','-f',name],capture_output=True,timeout=15)
    elif args.role=='inside':inside()
    elif args.role=='seed':seed()
    elif args.role in ('server','server-revoked'):serve(args.role=='server')
    elif args.role=='withdraw':
        context=json.loads(args.context);local('curated_publication').withdraw(CATALOG,[context['entry_id']],context['generation_sha256'],
            'synthetic-withdrawal',approve_withdrawal=True)
    elif args.role:print(json.dumps(asyncio.run(asyncio.wait_for(client(args.role,json.loads(args.context) if args.context else None),timeout=20))))
    else:parser.error('explicit isolated fixture option required')


if __name__=='__main__':main()
