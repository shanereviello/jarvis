"""Model-free actual stdio check of mounted source/policy and staged proposal state.

Run as Hermes UID1000 with JSON {entry, files} on stdin. Retains one harmless
pending receipt; no execution or publication authority is requested.
"""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import uuid

async def probe(payload):
    if os.getuid()!=1000:raise ValueError('Hermes UID1000 required')
    for path,h in payload['files'].items():
        p=Path(path)
        if p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest()!=h:raise ValueError('mounted source mismatch')
    entry=payload['entry'];args=entry['args'];state=Path(args[args.index('--state')+1])
    s=state.stat()
    if state.is_symlink() or not state.is_dir() or s.st_uid!=1000 or stat.S_IMODE(s.st_mode)!=0o700:raise ValueError('private staged state required')
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    params=StdioServerParameters(command=entry['command'],args=args,env={'PATH':'/usr/bin:/bin','HOME':'/opt/data'})
    def decoded(result):
        data=result.model_dump(by_alias=True)
        if data.get('isError'):raise ValueError('unexpected refusal')
        return data.get('structuredContent') or json.loads(result.content[0].text)
    async with stdio_client(params) as (read,write):
        async with ClientSession(read,write) as client:
            await client.initialize();listing=await client.list_tools()
            if {t.name for t in listing.tools}!={'prepare_coding_task','coding_task_proposal'}:raise ValueError('unexpected tool authority')
            request={'task_id':'TASK-preparation-acceptance-'+uuid.uuid4().hex,'repository_id':'robot_ws',
                     'objective':'Preparation-only installation acceptance. Do not execute this proposal.',
                     'allowed_paths':['src/pi/roboclaw_driver/config/roboclaw.yaml'],'validation_id':'manual-velocity'}
            result=decoded(await client.call_tool('prepare_coding_task',request))
            repeated=decoded(await client.call_tool('prepare_coding_task',request))
            if result['submission_id']!=repeated['submission_id']:raise ValueError('duplicate proposal changed')
            receipt=decoded(await client.call_tool('coding_task_proposal',{'submission_id':result['submission_id']}))
            if receipt['authenticated_identity']!='hermes' or receipt['execution_authorized'] or receipt['publication_authorized']:raise ValueError('unexpected approval')
            bad=await client.call_tool('prepare_coding_task',dict(request,repository_id='not-admitted'))
            if not bad.model_dump(by_alias=True).get('isError'):raise ValueError('unauthorized repository accepted')
            bad=await client.call_tool('prepare_coding_task',dict(request,allowed_paths=['outside.py']))
            if not bad.model_dump(by_alias=True).get('isError'):raise ValueError('unauthorized path accepted')
            if not (state/(result['submission_id']+'.json')).is_file():raise ValueError('receipt not retained')
    return {'scope':'installed-preparation-stdio-no-model','success':True,'uid':os.getuid(),'api_calls':0,
            'submission_id':result['submission_id'],'execution_authorized':False,'publication_authorized':False,
            'cases':['mounted_hashes','only_preparation_tools','proposal','duplicate','readback','fixed_identity','repo_refusal','scope_refusal','retained_receipt']}

if __name__=='__main__':
    payload=json.load(sys.stdin)
    result=asyncio.run(asyncio.wait_for(probe(payload),timeout=30))
    print(json.dumps(result))
