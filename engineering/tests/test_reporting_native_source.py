"""Selected cross-identity source RPC has no coding method or path discovery."""
import base64
import json
from pathlib import Path
import pytest
from test_reporting_capture_collectors import module
from test_reporting_codex_runtime import uid

m=module('native_source')


class Client:
    def __init__(self):
        self.calls=[];self.symlink=None;self.raw=(json.dumps(dict(type='session_meta',payload=dict(id=uid(5),cwd='/synthetic')))+'\n').encode()
    def call(self,method,params):
        self.calls.append((method,params));path=Path(params['path'])
        if method=='fs/getMetadata':return dict(isSymlink=str(path)==self.symlink,isFile=path.suffix=='.jsonl',isDirectory=path.suffix!='.jsonl',createdAtMs=0,modifiedAtMs=0)
        assert method=='fs/readFile';return dict(dataBase64=base64.b64encode(self.raw).decode())


def test_only_exact_registered_path_is_read_and_native_session_is_checked():
    client=Client();raw=m.read(client,'/native/sessions/year/selected.jsonl','/native/sessions',uid(5))
    assert raw==client.raw and client.calls[-1]==('fs/readFile',dict(path='/native/sessions/year/selected.jsonl'))
    with pytest.raises(ValueError):m.read(client,'/native/auth.json','/native/sessions',uid(5))
    assert len([c for c in client.calls if c[0]=='fs/readFile'])==1
    with pytest.raises(ValueError,match='session'):m.read(client,'/native/sessions/year/selected.jsonl','/native/sessions',uid(6))


@pytest.mark.parametrize('alias',['/native','/native/sessions','/native/sessions/year','/native/sessions/year/selected.jsonl'])
def test_symlink_in_any_native_ancestor_prevents_read(alias):
    client=Client();client.symlink=alias
    with pytest.raises(ValueError,match='metadata'):m.read(client,'/native/sessions/year/selected.jsonl','/native/sessions',uid(5))
    assert all(method!='fs/readFile' for method,_ in client.calls)


def test_oversized_source_and_coding_rpc_are_refused(monkeypatch):
    client=Client();monkeypatch.setattr(m,'MAX_SOURCE',16)
    with pytest.raises(ValueError,match='bounded'):m.read(client,'/native/sessions/selected.jsonl','/native/sessions',uid(5))
    source=object.__new__(m.Client)
    with pytest.raises(ValueError,match='no coding'):source.call('turn/start',{})
    with pytest.raises(ValueError,match='no coding'):source.call('fs/writeFile',{})


def test_private_channels_and_short_reasoning_are_removed_before_export_input():
    collect=module('capture_collectors')
    for row in (dict(type='response_item',payload=dict(type='reasoning',summary='short')),
                dict(type='response_item',payload=dict(type='message',role='assistant',phase='analysis',content='x')),
                dict(type='response_item',payload=dict(type='message',role='system',content='privileged')),
                dict(type='turn_context',payload=dict(developer_instructions='privileged'))):
        assert collect.codex_export_record(row) is None
    row=dict(type='session_meta',payload=dict(id=uid(5),cwd='/synthetic',base_instructions={'text':'privileged'},instructions='privileged'))
    assert collect.codex_export_record(row)['payload']==dict(id=uid(5),cwd='/synthetic')
    visible=dict(type='event_msg',payload=dict(type='agent_message',message='Visible engineering explanation.',reasoning='private'))
    assert collect.codex_export_record(visible)['payload']==dict(type='agent_message',message='Visible engineering explanation.')
