"""Read-only file transport and actual MCP stdio; no service/model calls."""
import asyncio
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import test_workflow_records as fixtures

ROOT = Path(__file__).resolve().parents[1] / 'tools/rras_native'


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


@pytest.fixture
def exported(tmp_path):
    j = module('workflow_journal')
    private = tmp_path / 'private'
    private.mkdir(mode=0o700)
    store = j.Journal(private, create=True)
    rows = fixtures.history()
    rows[-1]['summary'] = 'PRIVATE_NEVER_EXPORTED'
    store.append(rows)
    directory = tmp_path / 'views'
    directory.mkdir(mode=0o700)
    store.publish_jarvis(directory / 'work.json', rows[1]['work_item_id'])
    index = {'schema_version': 1, 'pages': [{'work_item_id': rows[1]['work_item_id'], 'after': 0, 'file': 'work.json'}]}
    (directory / 'index.json').write_text(json.dumps(index))
    return directory, rows[1]['work_item_id'], store


def tools(directory):
    class Server:
        def __init__(self): self.functions = {}
        def tool(self):
            def decorate(fn): self.functions[fn.__name__] = fn; return fn
            return decorate
    server = Server()
    module('workflow_read_tools').register(server, directory=directory)
    return server.functions


def test_only_read_tools_and_no_database_access(exported):
    directory, work_id, store = exported
    t = tools(directory)
    assert set(t) == {'workflow_pages', 'workflow_history'}
    with patch('sqlite3.connect', side_effect=AssertionError('reader must not open DB')):
        assert t['workflow_pages']()['pages'][0]['repository_id'] == 'jarvis'
        result = t['workflow_history'](work_id)
    assert 'PRIVATE_NEVER_EXPORTED' not in json.dumps(result)
    assert store.history(work_id)['events'][0]['summary'] == 'PRIVATE_NEVER_EXPORTED'


@pytest.mark.parametrize('filename', ['../private/workflow.sqlite3', '/etc/passwd', 'index.json', 'link.json'])
def test_index_cannot_choose_private_paths_or_symlinks(exported, filename):
    directory, work_id, store = exported
    (directory / 'link.json').symlink_to(store.path)
    (directory / 'index.json').write_text(json.dumps({'schema_version': 1, 'pages': [
        {'work_item_id': work_id, 'after': 0, 'file': filename}]}))
    with pytest.raises((ValueError, OSError)): tools(directory)['workflow_pages']()


def test_unknown_work_cursor_and_malformed_projection_refused(exported):
    directory, work_id, _ = exported
    t = tools(directory)
    for value in ('../private', 'wrk_' + 'f' * 32):
        with pytest.raises(ValueError): t['workflow_history'](value)
    with pytest.raises(ValueError): t['workflow_history'](work_id, 1)
    with pytest.raises(ValueError): t['workflow_pages'](0, 101)
    file = directory / 'work.json'
    value = json.loads(file.read_text())
    value['summary']['facts'][0]['private_log'] = 'PRIVATE'
    file.chmod(0o600)
    file.write_text(json.dumps(value))
    with pytest.raises(ValueError): t['workflow_pages']()


def test_real_stdio_lists_and_reads_only_projections(exported):
    directory, work_id, store = exported
    before = store.outbox()
    async def exercise():
        params = StdioServerParameters(command=sys.executable,
            args=['-I', '-B', str(ROOT / 'workflow_read_stdio.py'), '--directory', str(directory)],
            env={'PATH': '/usr/bin:/bin'})
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as client:
                await client.initialize()
                listing = await client.list_tools()
                assert {t.name for t in listing.tools} == {'workflow_pages', 'workflow_history'}
                result = await client.call_tool('workflow_history', {'work_item_id': work_id})
                assert not result.isError
                raw = json.dumps(result.model_dump(by_alias=True))
                assert 'PRIVATE_NEVER_EXPORTED' not in raw
                assert work_id in raw
                refused = await client.call_tool('workflow_history', {'work_item_id': '../private'})
                assert refused.isError
                assert 'PRIVATE_NEVER_EXPORTED' not in json.dumps(refused.model_dump(by_alias=True))
    asyncio.run(asyncio.wait_for(exercise(), timeout=30))
    assert store.outbox() == before


def test_stdio_scrubs_inherited_credentials_in_child(exported):
    directory, _, _ = exported
    code = '''import importlib.util,os,sys
s=importlib.util.spec_from_file_location('reader',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
os.environ.update(OPENAI_API_KEY='harmless-fixture',GITHUB_TOKEN='harmless-fixture')
m.server(sys.argv[2])
assert set(os.environ)<= {'PATH','HOME','LANG','LC_ALL'}
'''
    subprocess.run([sys.executable, '-I', '-B', '-c', code, str(ROOT / 'workflow_read_stdio.py'), str(directory)],
                   check=True, capture_output=True, timeout=15)
