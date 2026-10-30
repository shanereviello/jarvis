"""Read-only stdio MCP client for curated Unix search/read; no private fallback."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'vendor'))
ERROR='Curated history unavailable, refused or changed. Discard cached results and request a fresh authorized search.'


def local(name):
    spec=importlib.util.spec_from_file_location('curated_mcp_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def register(instance,*,socket,service_uid):
    @instance.tool()
    def engineering_history_search(repository_id:str,query:str='',generation_sha256:str|None=None,offset:int=0,limit:int=20):
        """Search explicitly selected curated history only; source claims may be stale or reported."""
        return local('curated_read_unix').call(socket,service_uid,{'method':'search','repository_id':repository_id,
            'query':query,'generation_sha256':generation_sha256,'offset':offset,'limit':limit})

    @instance.tool()
    def engineering_history_read(repository_id:str,entry_id:str,generation_sha256:str):
        """Read one exact current curated entry; withdrawn or stale generations refuse."""
        return local('curated_read_unix').call(socket,service_uid,{'method':'read','repository_id':repository_id,
            'entry_id':entry_id,'generation_sha256':generation_sha256})


def server(socket,service_uid,reader_uid):
    # Clear credentials/proxies/configuration before importing the MCP runtime.
    os.environ.clear();os.environ.update({'PATH':'/usr/bin:/bin','HOME':'/nonexistent','LANG':'C.UTF-8'})
    transport=local('unix');transport.uid(service_uid);transport.uid(reader_uid);transport.endpoint(socket)
    if os.getuid()!=reader_uid or os.geteuid()!=reader_uid or reader_uid==service_uid:raise ValueError('dedicated connected reader identity required')
    instructions=('Search only explicitly curated engineering history. Preserve source provenance, citations and unknown times. '
        'Recording is not task success, human approval or deployment. No private-history, publication or execution tool exists. '
        'Do not reuse cached content after a generation/refusal error; request a fresh authorized search.')
    from importlib.metadata import version
    major=int(version('mcp').split('.')[0])
    if major==1:
        from mcp.server.fastmcp import FastMCP
        # Normalize tool errors rather than returning source exceptions to the model.
        class SafeTools:
            def __init__(self,instance):self.instance=instance
            def tool(self):
                def decorate(fn):
                    import functools
                    @functools.wraps(fn)
                    def safe(*args,**kwargs):
                        try:return fn(*args,**kwargs)
                        except (ValueError,KeyError,TypeError,OSError):raise ValueError(ERROR) from None
                    self.instance.tool()(safe);return safe
                return decorate
        instance=FastMCP('rras-curated-engineering-history',instructions=instructions)
        register(SafeTools(instance),socket=socket,service_uid=service_uid)
        return instance
    if major!=2:raise ValueError('unreviewed MCP major version')
    import anyio
    import mcp.types as types
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    class Tools:
        def __init__(self):self.functions={}
        def tool(self):
            def decorate(fn):self.functions[fn.__name__]=fn;return fn
            return decorate
    tools=Tools();register(tools,socket=socket,service_uid=service_uid)
    schemas={
        'engineering_history_search':{'repository_id':{'type':'string'},'query':{'type':'string','maxLength':256},
            'generation_sha256':{'type':['string','null']},'offset':{'type':'integer','minimum':0},'limit':{'type':'integer','minimum':1,'maximum':50}},
        'engineering_history_read':{'repository_id':{'type':'string'},'entry_id':{'type':'string'},'generation_sha256':{'type':'string'}}}
    async def listing(context,params):
        return types.ListToolsResult(tools=[types.Tool(name=name,description=fn.__doc__,inputSchema={
            'type':'object','properties':schemas[name],
            'required':['repository_id'] if name=='engineering_history_search' else ['repository_id','entry_id','generation_sha256'],
            'additionalProperties':False}) for name,fn in tools.functions.items()])
    async def call(context,params):
        try:
            if params.name not in tools.functions:raise ValueError('unknown tool')
            result=tools.functions[params.name](**(params.arguments or {}))
            return types.CallToolResult(content=[types.TextContent(type='text',text=json.dumps(result))])
        except (ValueError,KeyError,TypeError,OSError):
            return types.CallToolResult(isError=True,content=[types.TextContent(type='text',text=ERROR)])
    instance=Server('rras-curated-engineering-history',instructions=instructions,on_list_tools=listing,on_call_tool=call)
    class Stdio:
        def run(self,transport):
            if transport!='stdio':raise ValueError('stdio only')
            async def serve():
                async with stdio_server() as (read,write):await instance.run(read,write,instance.create_initialization_options())
            anyio.run(serve)
    return Stdio()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--socket',required=True);parser.add_argument('--service-uid',type=int,required=True)
    parser.add_argument('--reader-uid',type=int,required=True);args=parser.parse_args(argv)
    try:server(args.socket,args.service_uid,args.reader_uid).run(transport='stdio')
    except (ValueError,KeyError,TypeError,OSError):parser.exit(1,ERROR+'\n')


if __name__=='__main__':main()
