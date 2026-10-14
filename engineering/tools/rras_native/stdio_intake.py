"""Hermes-local, preparation-only stdio MCP. No executor/provider/publication access."""
import argparse
import importlib.util
import os
from pathlib import Path


def server(policy, state):
    # Hermes may inherit API/tool credentials. This preparation child needs none.
    safe = {k: v for k, v in os.environ.items() if k in ('PATH', 'HOME', 'LANG', 'LC_ALL')}
    os.environ.clear()
    os.environ.update(safe)
    spec = importlib.util.spec_from_file_location('hermes_tools', Path(__file__).with_name('hermes_tools.py'))
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    instructions = (
        'Prepare coding task proposals only. A proposal is not an execution approval. '
        'Human approval is separately required to launch work and publish a GitHub branch. '
        'Use configured repository and validation IDs. No merge or deployment tools exist here.')
    from importlib.metadata import version
    major = int(version('mcp').split('.')[0])
    if major == 1:
        from mcp.server.fastmcp import FastMCP
        instance = FastMCP('rras-coding-preparation', instructions=instructions)
        adapter.register(instance, policy=policy, state=state, authenticated_identity=lambda: 'hermes')
        return instance
    if major != 2:
        raise ValueError('unreviewed MCP major version')
    # MCP 2 replaces FastMCP/decorators with explicit server callbacks.
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
    adapter.register(tools, policy=policy, state=state, authenticated_identity=lambda: 'hermes')
    schemas = {
        'prepare_coding_task': {'task_id': {'type':'string'}, 'repository_id': {'type':'string'},
            'objective': {'type':'string'}, 'allowed_paths': {'type':'array','items':{'type':'string'}},
            'validation_id': {'type':'string'}},
        'coding_task_proposal': {'submission_id': {'type':'string'}}}
    async def listing(context, params):
        return types.ListToolsResult(tools=[types.Tool(name=name, description=fn.__doc__,
            inputSchema={'type':'object','properties':schemas[name],'required':list(schemas[name]),
                         'additionalProperties':False}) for name,fn in tools.functions.items()])
    async def call(context, params):
        try:
            if params.name not in tools.functions: raise ValueError('unknown preparation tool')
            result = tools.functions[params.name](**(params.arguments or {}))
            return types.CallToolResult(content=[types.TextContent(type='text',text=json.dumps(result))])
        except (ValueError, KeyError, TypeError, OSError):
            # No proposal bodies, credentials or private paths in protocol error messages.
            return types.CallToolResult(isError=True,content=[types.TextContent(type='text',text='Proposal refused; check admitted identity, repository, paths and validation ID.')])
    instance = Server('rras-coding-preparation', instructions=instructions,
                      on_list_tools=listing, on_call_tool=call)
    class Stdio:
        def run(self, transport):
            if transport != 'stdio': raise ValueError('stdio only')
            async def serve():
                async with stdio_server() as (read,write):
                    await instance.run(read,write,instance.create_initialization_options())
            anyio.run(serve)
    return Stdio()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--policy', required=True)
    parser.add_argument('--state', required=True)
    args = parser.parse_args()
    server(args.policy, args.state).run(transport='stdio')
