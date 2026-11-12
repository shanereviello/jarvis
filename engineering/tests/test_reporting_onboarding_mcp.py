import importlib.util
from pathlib import Path
import os
import sys
import pytest
from jsonschema import ValidationError

path=Path(__file__).resolve().parents[1]/'tools/rras_reporting/onboarding_mcp.py'
spec=importlib.util.spec_from_file_location('onboarding_mcp_fixture',path)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_client_locks_dispatch_and_does_not_accept_actor_or_designation(tmp_path):
    dispatch='00000000-0000-4000-8000-000000000001'
    client=m.Client(tmp_path/'socket',1000,dispatch);calls=[]
    client.unix.call=lambda path,uid,request:calls.append((uid,request)) or {'execution_authorized':False}
    proposal=dict(name='Draft',overview='Overview',intended_outcome='Outcome',in_scope='Scope',out_of_scope='Other',
        markdown='# PLAN-01',plan_ids=['PLAN-01'])
    assert not client.call('engineering_draft_project',{'proposal':proposal})['execution_authorized']
    assert calls==[(1000,{'operation':'draft.project','dispatch_id':dispatch,'proposal':proposal})]
    with pytest.raises(ValidationError):client.call('engineering_draft_project',{'proposal':proposal,'dispatch_id':dispatch})
    with pytest.raises(ValueError):client.call('architecture_designate',{})


def test_launch_only_enables_the_two_planning_tools(tmp_path):
    dispatch='00000000-0000-4000-8000-000000000001'
    launch=m.Launch(tmp_path/'socket',1000,'/usr/bin/python3')
    config=launch.parameters(dispatch)
    tool=config['config']['mcp_servers']['engineering_planning']
    assert set(tool['enabled_tools'])=={'engineering_draft_project','engineering_draft_work'}
    assert tool['args'][-1]==dispatch and tool['required'] is True


def test_actual_mcp_stdio_exposes_only_planning_tools():
    import anyio
    from mcp import ClientSession,StdioServerParameters
    from mcp.client.stdio import stdio_client
    dispatch='00000000-0000-4000-8000-000000000001'
    params=StdioServerParameters(command=sys.executable,args=['-I',str(path),'--socket','/tmp/rras-planning-test.sock',
        '--service-uid',str(os.getuid()),'--dispatch',dispatch])
    async def run():
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write) as session:
                await session.initialize()
                result=await session.list_tools()
                assert {tool.name for tool in result.tools}=={'engineering_draft_project','engineering_draft_work'}
    anyio.run(run)
