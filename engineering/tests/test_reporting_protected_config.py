"""Installed policies cannot be replaced through writable ancestry or aliases."""
import json
import os
import pytest
from test_reporting_capture_collectors import module

m=module('protected_config')


def test_private_fixture_config_is_bounded_and_root_policy_is_required_by_default(tmp_path):
    folder=tmp_path/'installed';folder.mkdir(mode=0o700);path=folder/'config.json';path.write_text('{"fixture":true}');path.chmod(0o600)
    assert m.decode(path,require_root=False)==dict(fixture=True)
    if os.getuid()!=0:
        with pytest.raises(ValueError):m.decode(path)
    with pytest.raises(ValueError):m.read(path,maximum=2)
    path.chmod(0o644)
    with pytest.raises(ValueError):m.decode(path,require_root=False)


def test_config_symlink_hardlink_and_writable_parent_are_refused(tmp_path):
    folder=tmp_path/'installed';folder.mkdir(mode=0o700);path=folder/'config.json';path.write_text('{}');path.chmod(0o600)
    alias=folder/'alias';alias.symlink_to(path)
    with pytest.raises(ValueError):m.decode(alias,require_root=False)
    linked=folder/'linked';os.link(path,linked)
    with pytest.raises(ValueError):m.decode(path,require_root=False)
    linked.unlink();folder.chmod(0o777)
    with pytest.raises(ValueError):m.decode(path,require_root=False)


def test_native_adapter_registers_only_prose_reporting_tools():
    values=[]
    class Context:
        def register_tool(self,**value):values.append(value)
    module('hermes_runtime').register(Context(),'/not-a-selected-policy')
    assert {value['name'] for value in values}=={'engineering_checkpoint','engineering_handoff'}
    assert all(value['toolset']=='engineering_reporting' for value in values)
    for value in values:
        assert not {'work_item_id','session_id','run_id','approved','url','command'}&set(value['schema']['parameters']['properties'])
        result=json.loads(value['handler']({'key':'finding','observations':[],'next_step':'Retain context.'}))
        assert result['execution_started'] is False and 'error' in result and '/not-a-selected-policy' not in str(result)
