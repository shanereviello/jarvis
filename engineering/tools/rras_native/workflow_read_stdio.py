"""Read-only Jarvis workflow MCP over a fixed sanitized projection directory."""
import argparse
import importlib.util
import os
from pathlib import Path


def server(directory):
    safe = {k: v for k, v in os.environ.items() if k in ('PATH', 'HOME', 'LANG', 'LC_ALL')}
    os.environ.clear()
    os.environ.update(safe)
    spec = importlib.util.spec_from_file_location('workflow_read_tools', Path(__file__).with_name('workflow_read_tools.py'))
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    adapter.pages(directory)  # Fail closed before serving a malformed index.
    instructions = ('Read explicitly exported workflow history only. Exports are snapshots; '
                    'provenance distinguishes observed and reported claims. No write, approval, '
                    'execution, artifact-download, publication or deployment tool exists.')
    from importlib.metadata import version
    major = int(version('mcp').split('.')[0])
    if major == 1:
        from mcp.server.fastmcp import FastMCP
        instance = FastMCP('rras-workflow-history', instructions=instructions)
        adapter.register(instance, directory=directory)
        return instance
    if major != 2:
        raise ValueError('unreviewed MCP major version')
    import json
    import anyio
    import mcp.types as types
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    class Tools:
        def __init__(self): self.functions = {}
        def tool(self):
            def decorate(fn): self.functions[fn.__name__] = fn; return fn
            return decorate
    tools = Tools()
    adapter.register(tools, directory=directory)
    schemas = {
        'workflow_pages': {'offset': {'type': 'integer', 'minimum': 0}, 'limit': {'type': 'integer', 'minimum': 1, 'maximum': 100}},
        'workflow_history': {'work_item_id': {'type': 'string', 'pattern': '^wrk_[0-9a-f]{32}$'}, 'after': {'type': 'integer', 'minimum': 0}}}
    async def listing(context, params):
        return types.ListToolsResult(tools=[types.Tool(name=name, description=fn.__doc__,
            inputSchema={'type': 'object', 'properties': schemas[name],
                         'required': ['work_item_id'] if name == 'workflow_history' else [], 'additionalProperties': False})
                         for name, fn in tools.functions.items()])
    async def call(context, params):
        try:
            if params.name not in tools.functions: raise ValueError('unknown history tool')
            result = tools.functions[params.name](**(params.arguments or {}))
            return types.CallToolResult(content=[types.TextContent(type='text', text=json.dumps(result))])
        except (ValueError, KeyError, TypeError, OSError):
            return types.CallToolResult(isError=True, content=[types.TextContent(type='text', text='History unavailable; check projection identity, cursor and freshness with the operator.')])
    instance = Server('rras-workflow-history', instructions=instructions, on_list_tools=listing, on_call_tool=call)
    class Stdio:
        def run(self, transport):
            if transport != 'stdio': raise ValueError('stdio only')
            async def serve():
                async with stdio_server() as (read, write):
                    await instance.run(read, write, instance.create_initialization_options())
            anyio.run(serve)
    return Stdio()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', required=True)
    args = parser.parse_args()
    server(args.directory).run(transport='stdio')
