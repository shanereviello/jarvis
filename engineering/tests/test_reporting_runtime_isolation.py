"""Protected native Unix RPC and narrowly bound reporting broker behavior."""
import json
import os
import socket
import sys
import threading
import pytest
from test_reporting_runtime_reporting import setup,m,projects,store,reporting
from test_reporting_codex_runtime import m as runtime_module,Client,uid,runtime,policy


def native_listener(tmp_path):
    directory=tmp_path/'run';directory.mkdir(mode=0o700);path=directory/'native.sock'
    listener=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);listener.bind(str(path));path.chmod(0o600);listener.listen(1)
    seen=[]
    def serve():
        with listener.accept()[0] as connection,connection.makefile('rwb') as stream:
            while raw:=stream.readline():
                value=json.loads(raw);seen.append(value)
                if 'id' in value:
                    stream.write(runtime_module.encoded(dict(id=value['id'],result=dict(observed_method=value['method']))));stream.flush()
    thread=threading.Thread(target=serve,daemon=True);thread.start()
    return path,listener,thread,seen


def test_native_socket_rpc_checks_peer_before_sending_and_preserves_protocol(tmp_path):
    path,listener,thread,seen=native_listener(tmp_path)
    client=runtime_module.SocketAppServer(path,os.getuid())
    try:assert client.call('thread/read',dict(threadId='synthetic',includeTurns=True))==dict(observed_method='thread/read')
    finally:client.close();thread.join(timeout=3);listener.close()
    assert [x['method'] for x in seen]==['initialize','initialized','thread/read']
    assert all('Authorization' not in str(x) for x in seen)


def test_wrong_native_listener_uid_receives_no_private_request(tmp_path):
    path,listener,thread,seen=native_listener(tmp_path)
    try:
        with pytest.raises(ValueError,match='identity differs'):runtime_module.SocketAppServer(path,os.getuid()+1)
    finally:thread.join(timeout=3);listener.close()
    assert seen==[]


def test_broker_supplies_exact_active_context_and_refuses_stale_selector(tmp_path,projects,reporting):
    policy,config,spool,reporter,request=setup(tmp_path,projects);client=Client()
    runtime=runtime_module.Runtime(tmp_path/'runtime',policy,create=True,client_factory=lambda *a:client,reporter=reporter)
    try:
        runtime.dispatch(request);broker=m.local('runtime_checkpoint_broker').Access(runtime,config,os.getuid()+1)
        message=dict(method='checkpoint',session_id=uid(5),dispatch_id=uid(4),arguments=dict(key='broker-finding',
            observations=['Observed a selected failure.'],next_step='Validate the correction.'))
        value=broker.dispatch(os.getuid()+1,message)
        assert value['work_item_id']==request['binding']['work_id'] and not value['authority_granted']
        with pytest.raises(ValueError):broker.dispatch(os.getuid(),message)
        for changed in (dict(message,session_id=uid(99)),dict(message,dispatch_id=uid(99)),dict(message,method='project_read'),dict(message,work_item_id='spoof')):
            with pytest.raises(ValueError):broker.dispatch(os.getuid()+1,changed)
        client.finish('completed');runtime.status(uid(4))
        with pytest.raises(ValueError):broker.dispatch(os.getuid()+1,message)
    finally:runtime.close()


def test_native_mcp_configuration_contains_no_parent_paths_or_bridge_credential(tmp_path):
    launch=m.local('runtime_checkpoint_mcp').BrokerLaunch(tmp_path/'report.sock',os.getuid(),sys.executable)
    value=launch.parameters(uid(5),uid(4));args=value['config']['mcp_servers']['engineering_checkpoint']['args']
    assert args[-4:]==['--session',uid(5),'--dispatch',uid(4)]
    assert '--state' not in args and '--reporting-policy' not in args and '--bridge-token-file' not in args
    tool=value['config']['mcp_servers']['engineering_checkpoint']
    assert tool['tools']=={'engineering_checkpoint': {'approval_mode':'approve'}}


def test_visible_native_result_is_redacted_before_transport_publication(runtime,policy):
    value,client=runtime
    from test_reporting_codex_runtime import request as dispatch
    value.dispatch(dispatch(policy));client.finish('completed')
    client.waiting[0]['params']['item']['text']='Visible diagnostic api_key=sk-fixture-DO-NOT-RETAIN-123456789'
    result=value.status(uid(4));assert 'sk-fixture-DO-NOT-RETAIN' not in result['result']
    with value.connection() as db:assert 'sk-fixture-DO-NOT-RETAIN' in db.execute('SELECT result FROM turns').fetchone()[0]
