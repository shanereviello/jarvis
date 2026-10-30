"""Pinned-image synthetic MCP client; no production mounts or provider calls."""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import sys

ROOT=Path('/opt/curated-fixture')
sys.path.insert(0,str(ROOT/'vendor'))
SERVICE=61151
CLIENT=61152
SOCKET='/run/curated-fixture/read.sock'


def local(name):
    p=ROOT/'engineering/tools/rras_history'/(name+'.py')
    spec=importlib.util.spec_from_file_location('image_probe_'+name,p);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def boundary(uid):
    if os.getuid()!=uid or os.geteuid()!=uid or os.getgid()!=uid or os.getgroups():raise ValueError('container identity differs')
    info=dict(line.split(':',1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
    if info['NoNewPrivs'].strip()!='1' or any(int(info[key].strip(),16) for key in ('CapEff','CapPrm','CapInh','CapBnd','CapAmb')):raise ValueError('container privileges retained')
    interfaces={line.split(':',1)[0].strip() for line in Path('/proc/self/net/dev').read_text().splitlines() if ':' in line}
    if interfaces!={'lo'} or Path('/proc/self/net/route').read_text().splitlines()[1:]:raise ValueError('container network differs')
    if set(os.environ)-{'PATH','HOME','LANG'}:raise ValueError('container provider environment retained')


def is_error(result):
    # SDK 2 client models expose snake_case; SDK 1 uses the wire spelling.
    if hasattr(result,'is_error'):return result.is_error is True
    return result.isError is True


def value(result):
    if is_error(result):raise ValueError('expected successful MCP result')
    return json.loads(result.content[0].text)


async def client(role,context):
    from mcp import ClientSession,StdioServerParameters
    from mcp.client.stdio import stdio_client
    params=StdioServerParameters(command='/opt/hermes/.venv/bin/python',args=['-I','-B',
        str(ROOT/'engineering/tools/rras_history/curated_mcp.py'),'--socket',SOCKET,'--service-uid',str(SERVICE),'--reader-uid',str(CLIENT)],env=dict(os.environ))
    async with stdio_client(params) as (read,write):
        async with ClientSession(read,write) as session:
            await session.initialize()
            tools=await session.list_tools()
            if {tool.name for tool in tools.tools}!={'engineering_history_search','engineering_history_read'}:raise ValueError('MCP authority expanded')
            async def search(**extra):return await session.call_tool('engineering_history_search',{'repository_id':'example_library',**extra})
            if role=='revoked':
                if not is_error(await search()):raise ValueError('revoked client retrieved content')
                return {'revoked':True}
            page=value(await search())
            if role=='read':
                if len(page['entries'])!=1 or page['entries'][0]['summary']!='Curated example_library':raise ValueError('curated result differs')
                entry=page['entries'][0];context={'entry_id':entry['entry_id'],'generation_sha256':page['generation_sha256']}
                exact=value(await session.call_tool('engineering_history_read',{'repository_id':'example_library',**context}))
                if exact['entry']!=entry or exact['authority_granted'] is not False or exact['human_authenticated'] is not False:raise ValueError('MCP read evidence differs')
                if not is_error(await session.call_tool('engineering_history_search',{'repository_id':'other_repo'})):raise ValueError('other repository accessible')
                if not is_error(await session.call_tool('publish',{})):raise ValueError('publication tool accessible')
                if b'SYNTHETIC PRIVATE' in json.dumps(page).encode():raise ValueError('private prose disclosed')
                for method in ('history','document','publish','withdraw','approve','launch','merge','deploy'):
                    try:local('curated_read_unix').call(SOCKET,SERVICE,{'method':method,'repository_id':'example_library'})
                    except (ValueError,OSError):pass
                    else:raise ValueError('private/action socket route accessible')
                return {'exact_mcp_read':True,'context':context}
            if role!='withdrawn' or page['entries']:raise ValueError('withdrawal differs')
            if not is_error(await search(generation_sha256=context['generation_sha256'])):raise ValueError('stale search accessible')
            if not is_error(await session.call_tool('engineering_history_read',{'repository_id':'example_library',**context})):raise ValueError('stale entry accessible')
            return {'withdrawn_and_stale_refused':True}


def main(role,uid):
    boundary(uid)
    if role=='denied':
        try:local('curated_read_unix').call(SOCKET,SERVICE,{'method':'search','repository_id':'example_library','query':'','generation_sha256':None,'offset':0,'limit':20})
        except (ValueError,OSError):return {'ungranted_peer_denied':True,'uid':uid}
        raise ValueError('ungranted peer retrieved content')
    if uid!=CLIENT:raise ValueError('wrong MCP client identity')
    context=json.loads(sys.stdin.buffer.read(4096) or b'{}')
    return asyncio.run(client(role,context))


if __name__=='__main__':print(json.dumps(main(sys.argv[1],int(sys.argv[2]))))
