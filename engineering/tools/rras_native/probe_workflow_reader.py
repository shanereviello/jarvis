"""Model-free actual-container stdio check from temporary synthetic files only.

Read JSON {files:{relative_name:{sha256,base64}}} on stdin. Never reads live Hermes
configuration, private journal state or credentials; no container restart needed.
"""
import asyncio
import base64
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import tempfile

ALLOWED = {'engineering/tools/rras_native/' + name for name in (
    'activity.py', 'workflow_records.py', 'workflow_journal.py',
    'workflow_read_tools.py', 'workflow_read_stdio.py')}
ALLOWED |= {'engineering/contracts/workflow-v1.schema.json', 'views/index.json', 'views/work.json'}


async def probe(payload):
    if os.getuid() != 1000 or set(payload) != {'files'} or set(payload['files']) != ALLOWED:
        raise ValueError('exact UID1000 reader fixture bundle required')
    with tempfile.TemporaryDirectory(prefix='rras-workflow-reader-acceptance-') as temporary:
        root = Path(temporary)
        for name, entry in payload['files'].items():
            if set(entry) != {'sha256', 'base64'}:
                raise ValueError('invalid fixture entry')
            raw = base64.b64decode(entry['base64'], validate=True)
            if len(raw) > 512 * 1024 or hashlib.sha256(raw).hexdigest() != entry['sha256']:
                raise ValueError('fixture digest mismatch')
            path = root / name
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            path.write_bytes(raw)
            path.chmod(0o444)
        index = json.loads((root / 'views/index.json').read_text())
        work_id = index['pages'][0]['work_item_id']
        server = root / 'engineering/tools/rras_native/workflow_read_stdio.py'
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        params = StdioServerParameters(command=sys.executable,
            args=['-I', '-B', str(server), '--directory', str(root / 'views')],
            env={'PATH': '/usr/bin:/bin', 'HOME': str(root)})
        def decoded(result):
            data = result.model_dump(by_alias=True)
            if data.get('isError'):
                raise ValueError('reader refused synthetic valid page')
            return data.get('structuredContent') or json.loads(result.content[0].text)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as client:
                await client.initialize()
                listing = await client.list_tools()
                if {tool.name for tool in listing.tools} != {'workflow_pages', 'workflow_history'}:
                    raise ValueError('unexpected tool authority')
                pages = decoded(await client.call_tool('workflow_pages', {}))
                if len(pages['pages']) != 1 or pages['pages'][0]['work_item_id'] != work_id:
                    raise ValueError('fixture page listing mismatch')
                view = decoded(await client.call_tool('workflow_history', {'work_item_id': work_id}))
                if view['summary']['work_item_id'] != work_id or view['summary']['release_status'] != 'not_inferred':
                    raise ValueError('fixture readback mismatch')
                if any(key in json.dumps(view) for key in ('PRIVATE_FIXTURE_TEXT', 'private_log', 'objective', 'validation_argv')):
                    raise ValueError('private fixture field exposed')
                for arguments in ({'work_item_id': '../private'}, {'work_item_id': work_id, 'after': 999}):
                    result = await client.call_tool('workflow_history', arguments)
                    if not result.model_dump(by_alias=True).get('isError'):
                        raise ValueError('invalid identity/cursor accepted')
        return {'phase': 'actual_hermes_reader_stdio_verified', 'uid': os.getuid(),
                'mcp_version': importlib.metadata.version('mcp'), 'api_calls': 0,
                'temporary_fixture_removed': True, 'live_configuration_changed': False,
                'read_only_mount_tested': False,
                'cases': ['exact_source_hashes', 'only_read_tools', 'list', 'readback',
                          'private_fields_omitted', 'identity_refusal', 'cursor_refusal']}


if __name__ == '__main__':
    raw = sys.stdin.buffer.read(4 * 1024 * 1024 + 1)
    if len(raw) > 4 * 1024 * 1024:
        raise ValueError('oversized fixture bundle')
    print(json.dumps(asyncio.run(asyncio.wait_for(probe(json.loads(raw)), timeout=40))))
