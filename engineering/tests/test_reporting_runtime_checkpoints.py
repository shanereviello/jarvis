"""Scoped intermediate checkpoints use actual active runtime context, not tool text."""
import copy
import asyncio
import json
import sys
from datetime import timedelta
import pytest
from test_reporting_runtime_reporting import setup,m,projects,store,reporting,evidence,sender,events
from test_reporting_codex_runtime import m as runtime_module,Client,uid


def active(tmp_path,projects):
    policy,config,spool,reporter,request=setup(tmp_path,projects);client=Client()
    runtime=runtime_module.Runtime(tmp_path/'runtime',policy,create=True,client_factory=lambda *a:client,reporter=reporter)
    runtime.dispatch(request)
    checkpoints=m.local('runtime_checkpoint_mcp').Checkpoints(runtime.root,config,uid(5))
    return runtime,client,checkpoints,spool,request


def test_meaningful_checkpoint_is_redacted_bound_and_exactly_replayed(tmp_path,projects,reporting,evidence):
    runtime,client,tool,spool,request=active(tmp_path,projects)
    try:
        args=dict(key='test-failure-1',observations=['Found missing test setup; api_key=sk-fixture-DO-NOT-RETAIN-123456789'],
            next_step='Correct the fixture and rerun the focused test.',validation=[dict(result='failed',description='Fixture failed before execution.',
                references=[],criterion_id='fixture-replay',command='pytest -q selected_test',code_commit='a'*40,
                environment='synthetic-local',output_sha256='b'*64)])
        first=tool.record(args);assert tool.record(args)==first
        assert first['work_item_id']==request['binding']['work_id'] and not first['authority_granted']
        assert spool.flush(sender(reporting))['pending']==0
        rows=[r for r,_ in events(reporting)]
        saved=next(r for r in rows if r['operation']=='checkpoint.report' and 'Found missing' in str(r['body']))
        assert saved['context']==tool.reporter.configuration['contexts'][uid(3)]
        assert saved['body']['attempt_id'].startswith('att_') and saved['body']['validation'][0]['result']=='failed'
        assert b'sk-fixture-DO-NOT-RETAIN' not in spool.c.encoded(saved)
        assert sum(method=='turn/start' for method,_ in client.calls)==1
        changed=copy.deepcopy(args);changed['next_step']='A different step'
        with pytest.raises(ValueError,match='key changed'):tool.record(changed)
    finally:runtime.close()


def test_caller_cannot_select_work_or_spoof_attempt_and_terminal_session_refuses(tmp_path,projects,reporting):
    runtime,client,tool,spool,request=active(tmp_path,projects)
    try:
        from jsonschema import ValidationError
        args=dict(key='finding',observations=['Observed a boundary.'],next_step='Verify it.')
        for field in ('project_id','work_item_id','attempt_id','report_id','approved'):
            with pytest.raises(ValidationError):tool.record(dict(args,**{field:'caller-chosen'}))
        wrong=m.local('runtime_checkpoint_mcp').Checkpoints(runtime.root,tool.reporter.configuration,uid(99))
        with pytest.raises(ValueError,match='active'):wrong.record(args)
        client.finish('completed');runtime.status(uid(4))
        with pytest.raises(ValueError,match='active'):tool.record(args)
    finally:runtime.close()


def test_changed_frozen_dispatch_is_not_used_for_attribution(tmp_path,projects,reporting):
    runtime,client,tool,spool,request=active(tmp_path,projects)
    try:
        with runtime.connection() as db:db.execute("UPDATE turns SET digest=?",('0'*64,))
        with pytest.raises(ValueError,match='frozen'):tool.record(dict(key='finding',observations=['Visible.'],next_step='Verify.'))
    finally:runtime.close()


def test_actual_mcp_stdio_lists_only_scoped_recorder_and_stages_checkpoint(tmp_path,projects,reporting):
    from mcp import ClientSession,StdioServerParameters
    from mcp.client.stdio import stdio_client
    runtime,client,tool,spool,request=active(tmp_path,projects)
    configuration=tmp_path/'reporting-policy.json';configuration.write_text(json.dumps(tool.reporter.configuration));configuration.chmod(0o600)
    async def check():
        params=StdioServerParameters(command=sys.executable,args=['-I','-B',str(m.Path(m.__file__).with_name('runtime_checkpoint_mcp.py')),
            '--state',str(runtime.root),'--reporting-policy',str(configuration),'--session',uid(5)],
            env=dict(PATH='/usr/bin:/bin',HOME='/nonexistent',LANG='C.UTF-8'))
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write,read_timeout_seconds=timedelta(seconds=10)) as session:
                await session.initialize();tools=await session.list_tools()
                assert {t.name for t in tools.tools}=={'engineering_checkpoint'}
                result=await session.call_tool('engineering_checkpoint',dict(key='native-sdk-check',observations=['Fixture SDK delivery verified.'],next_step='Keep source-only acceptance separate.'))
                assert not result.isError and json.loads(result.content[0].text)['staged']
                refused=await session.call_tool('engineering_checkpoint',dict(key='spoof',observations=[],next_step='Unknown.',work_item_id='caller-chosen'))
                assert refused.isError
    try:asyncio.run(check())
    finally:runtime.close()


def test_thread_registration_and_inventory_preserve_one_recorder_identity(tmp_path,projects,reporting):
    policy,config,spool,reporter,request=setup(tmp_path,projects)
    configuration=tmp_path/'reporting.json';configuration.write_text(json.dumps(config));configuration.chmod(0o600)
    root=tmp_path/'state';root.mkdir(mode=0o700)
    launch=m.local('runtime_checkpoint_mcp').Launch(root,configuration,sys.executable)
    class InventoryClient(Client):
        unexpected=False
        def call(self,method,params):
            if method=='mcpServerStatus/list':
                self.calls.append((method,params))
                servers=[dict(name='engineering_checkpoint',runtimeStatus='connected',tools={'engineering_checkpoint':{}})]
                if self.unexpected:servers.append(dict(name='personal_linear',runtimeStatus='connected',tools={'write':{}}))
                return dict(data=servers,nextCursor=None)
            return super().call(method,params)
    client=InventoryClient();runtime=runtime_module.Runtime(root/'runtime',policy,create=True,reporter=reporter,
        checkpoint_tool=launch,client_factory=lambda *a:client)
    try:
        assert runtime.dispatch(request)['state']=='running'
        start=next(params for method,params in client.calls if method=='thread/start')
        assert set(start['config']['mcp_servers'])=={'engineering_checkpoint'}
        assert start['config']['mcp_servers']['engineering_checkpoint']['args'][-1]==uid(5)
        client.finish('completed');runtime.status(uid(4));client.unexpected=True
        next_request=copy.deepcopy(request);next_request['dispatch_id']=uid(88)
        with pytest.raises(ValueError,match='uncertain'):runtime.dispatch(next_request)
        assert sum(method=='turn/start' for method,_ in client.calls)==1
    finally:runtime.close()
