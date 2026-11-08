"""Actual active-context staging and safe replay without OAuth or model calls."""
import copy
import os
import sqlite3
import sys
from pathlib import Path
import pytest
from test_reporting_runtime_reporting import setup,m,projects,reporting,store
from test_reporting_codex_runtime import m as native,Client,uid


handoff=m.local('runtime_handoff')


def arguments():return dict(key='selected-assistant-context',summary='Explain the retained outcome.',
    requested_action='Summarize the investigation for the operator; engineering ownership remains Codex.',references=[],limitations=['No new code baseline was independently inspected.'])


def installed(tmp_path,projects):
    policy,config,spool,_,request=setup(tmp_path,projects)
    queue=handoff.Queue(tmp_path/'handoff-queue',create=True)
    config['handoff']=dict(spool=str(queue.path),policy=dict(contract='native-agent-handoff-policy.v1',
        organization_id=policy['organization_id'],agents=dict(codex=policy['app_user_id'],jarvis=uid(20)),issues=policy['issues']))
    reporter=m.Reporter(config,policy);client=Client()
    runtime=native.Runtime(tmp_path/'runtime',policy,create=True,reporter=reporter,client_factory=lambda *a:client)
    return runtime,config,spool,queue,request,client


def test_native_tool_uses_actual_context_and_stages_no_execution(tmp_path,projects,reporting):
    runtime,config,spool,queue,request,client=installed(tmp_path,projects)
    try:
        runtime.dispatch(request);broker=m.local('runtime_checkpoint_broker').Access(runtime,config,os.getuid()+1)
        message=dict(method='handoff',session_id=request['session_id'],dispatch_id=request['dispatch_id'],arguments=arguments())
        result=broker.dispatch(os.getuid()+1,message)
        assert result['staged'] and not result['execution_started']
        assert broker.dispatch(os.getuid()+1,message)['replayed']
        with queue.connection() as db:saved=queue.i.local('contract').decode(db.execute('SELECT intent FROM handoffs').fetchone()[0])
        assert saved['binding']==request['binding'] and saved['source_session_id']==request['session_id']
        assert saved['sender']=='codex' and saved['recipient']=='jarvis' and saved['depth']==1 and saved['parent_handoff_id'] is None
        assert sum(method=='turn/start' for method,_ in client.calls)==1
        changed=dict(message,arguments=dict(arguments(),summary='Changed under the original key'))
        with pytest.raises(ValueError,match='key changed'):broker.dispatch(os.getuid()+1,changed)
        for field in ('session_id','dispatch_id'):
            with pytest.raises(ValueError):broker.dispatch(os.getuid()+1,dict(message,**{field:uid(99)}))
        client.finish('completed');runtime.status(request['dispatch_id'])
        with pytest.raises(ValueError):broker.dispatch(os.getuid()+1,message)
    finally:runtime.close()


def test_incoming_chain_is_retained_in_return_and_coordinator(tmp_path,projects,reporting):
    runtime,config,spool,queue,request,client=installed(tmp_path,projects)
    chain=dict(id=uid(80),depth=2,source_session_id=uid(81),sender_app_user_id=uid(20),
        recipient_app_user_id=uid(2),target_session_id=uid(5))
    request['incoming_handoff']=chain
    try:
        runtime.dispatch(request);broker=m.local('runtime_checkpoint_broker').Access(runtime,config,os.getuid()+1)
        broker.dispatch(os.getuid()+1,dict(method='handoff',session_id=uid(5),dispatch_id=uid(4),arguments=arguments()))
        with queue.connection() as db:value=queue.i.local('contract').decode(db.execute('SELECT intent FROM handoffs').fetchone()[0])
        assert value['parent_handoff_id']==chain['id'] and value['depth']==3
        with spool.connection() as db:rows=[spool.c.decode(r[0]) for r in db.execute('SELECT request FROM items')]
        attempts=[r['body'] for r in rows if r['operation']=='attempt.record']
        assert attempts and all(a['coordinator']==dict(role='jarvis',runtime='hermes',source_actor_id=uid(20)) for a in attempts)
    finally:runtime.close()


@pytest.mark.parametrize('field,value',[('depth',True),('depth',5),('target_session_id',uid(99)),('sender_app_user_id',uid(2)),('recipient_app_user_id',uid(20))])
def test_wrong_incoming_context_never_reaches_native(tmp_path,projects,reporting,field,value):
    runtime,config,spool,queue,request,client=installed(tmp_path,projects)
    chain=dict(id=uid(80),depth=1,source_session_id=uid(81),sender_app_user_id=uid(20),recipient_app_user_id=uid(2),target_session_id=uid(5))
    request['incoming_handoff']=dict(chain,**{field:value})
    try:
        with pytest.raises(ValueError):runtime.dispatch(request)
        assert client.calls==[]
    finally:runtime.close()


def test_queue_loss_replays_original_admission_and_never_deletes(tmp_path):
    queue=handoff.Queue(tmp_path/'queue',create=True)
    intent=dict(id=uid(40),contract='synthetic');queue.stage(intent)
    seen=[]
    def lost(value):seen.append(value);raise OSError('synthetic lost admission acknowledgment')
    assert queue.flush(lost)==dict(delivered=0,pending=1,models_started=0)
    restarted=handoff.Queue(queue.path)
    def accepted(value):
        seen.append(value);return dict(staged=True,request_id=value['id'],execution_started=False)
    assert restarted.flush(accepted)==dict(delivered=1,pending=0,models_started=0)
    assert seen==[intent,intent]
    assert restarted.flush(accepted)['delivered']==0
    with restarted.connection() as db:
        with pytest.raises(sqlite3.IntegrityError):db.execute('DELETE FROM handoffs')
        with pytest.raises(sqlite3.IntegrityError):db.execute("UPDATE handoffs SET intent='changed'")


def test_native_tool_has_no_private_transport_configuration(tmp_path):
    # The isolated test virtualenv is deliberately user-writable and cannot
    # stand in for the root-owned interpreter required on the production host.
    module=m.local('runtime_checkpoint_mcp')
    with pytest.raises(ValueError,match='trusted installed MCP Python'):
        module.BrokerLaunch(tmp_path/'broker.sock',os.getuid(),sys.executable,handoff=True)
    # Exercise only the public MCP configuration shape without pretending the
    # test interpreter passed the production trust check.
    tool=module.BrokerLaunch.__new__(module.BrokerLaunch)
    tool.socket=tmp_path/'broker.sock';tool.service_uid=os.getuid();tool.python=Path('/usr/bin/python3');tool.handoff_enabled=True
    params=tool.parameters(uid(5),uid(4));entry=params['config']['mcp_servers']['engineering_checkpoint']
    assert entry['enabled_tools']==['engineering_checkpoint','engineering_handoff']
    assert '--handoff' in entry['args']
    assert all(word not in str(params) for word in ('token_file','OAuth','handoffs.sqlite3'))


def test_independent_delivery_remains_fair_past_a_full_page_of_blocked_reports(tmp_path):
    queue=handoff.Queue(tmp_path/'queue',create=True)
    for number in range(40):queue.stage(dict(id=uid(number+100),fixture=True))
    seen=[]
    def send(value):
        seen.append(value['id'])
        if value['id']!=uid(139):raise ValueError('synthetic pending context')
        return dict(staged=True,request_id=value['id'],execution_started=False)
    assert queue.flush(send,independent=True)['delivered']==0
    assert queue.flush(send,independent=True)['delivered']==1 and uid(139) in seen
