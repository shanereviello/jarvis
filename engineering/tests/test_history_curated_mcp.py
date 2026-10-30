"""MCP wire discovery/refusal and request mapping; distinct-UID success is a host gate."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from test_engineering_history_local import module

SCRIPT=Path(__file__).resolve().parents[1]/'tools/rras_history/curated_mcp.py'


def test_actual_stdio_discovery_and_unavailable_refusal():
    async def exercise():
        params=StdioServerParameters(command=sys.executable,args=['-I','-B',str(SCRIPT),'--socket','/run/rras-fixture-absent/read.sock',
            '--service-uid','995','--reader-uid',str(os.getuid())],env={'PATH':'/usr/bin:/bin'})
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write) as client:
                await client.initialize();listing=await client.list_tools()
                assert {tool.name for tool in listing.tools}=={'engineering_history_search','engineering_history_read'}
                result=await client.call_tool('engineering_history_search',{'repository_id':'jarvis'})
                assert result.isError and 'Discard cached results' in result.content[0].text
                assert '/run/rras-fixture-absent' not in result.content[0].text
    asyncio.run(asyncio.wait_for(exercise(),timeout=30))


def test_register_maps_only_two_read_methods(monkeypatch):
    m=module('curated_mcp');calls=[]
    class Tools:
        def __init__(self):self.functions={}
        def tool(self):
            def register(fn):self.functions[fn.__name__]=fn;return fn
            return register
    def call(path,uid,message):calls.append((path,uid,message));return {'authority_granted':False}
    monkeypatch.setattr(m,'local',lambda _:SimpleNamespace(call=call))
    tools=Tools();m.register(tools,socket='/fixture/read.sock',service_uid=995)
    assert set(tools.functions)=={'engineering_history_search','engineering_history_read'}
    tools.functions['engineering_history_search']('jarvis','why',None,0,20)
    tools.functions['engineering_history_read']('jarvis','cur_'+'a'*64,'b'*64)
    assert calls[0]==('/fixture/read.sock',995,{'method':'search','repository_id':'jarvis','query':'why','generation_sha256':None,'offset':0,'limit':20})
    assert calls[1][2]['method']=='read'


def test_environment_scrub_and_distinct_identity_refusal_in_child():
    code='''import importlib.util,os,sys
s=importlib.util.spec_from_file_location('client',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
os.environ.update(OPENAI_API_KEY='fixture',GITHUB_TOKEN='fixture',HTTP_PROXY='fixture')
for service,reader in [(995,os.getuid()+10000),(os.getuid(),os.getuid())]:
 try:m.server('/run/absent.sock',service,reader)
 except ValueError:pass
 else:raise AssertionError('identity guard accepted')
assert set(os.environ)<={'PATH','HOME','LANG'}
'''
    subprocess.run([sys.executable,'-I','-B','-c',code,str(SCRIPT)],check=True,capture_output=True,timeout=15)
