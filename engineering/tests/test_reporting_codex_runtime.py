"""Model-free runtime protocol, actual journal restart, cancellation and HTTP tests."""
import copy
import importlib.util
import json
from pathlib import Path
import threading
import urllib.error
import urllib.request
import uuid

import pytest

ROOT = Path(__file__).resolve().parents[1]
def module(name):
    spec = importlib.util.spec_from_file_location('runtime_test_'+name, ROOT/'tools/rras_reporting'/(name+'.py'))
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value); return value
m = module('codex_runtime')
def uid(n): return str(uuid.UUID(int=n))


class Client:
    def __init__(self, *args): self.calls=[]; self.waiting=[]; self.closed=False; self.fail=None; self.complete=False
    def call(self, method, params):
        self.calls.append((method,params))
        if self.fail == method: raise ValueError('synthetic lost response')
        if method.startswith('thread/'):
            return dict(thread=dict(id='thread-1',sessionId='root-lineage-1'))
        if method == 'turn/start':
            if self.complete: self.finish('completed')
            return dict(turn=dict(id='turn-'+str(sum(k=='turn/start' for k,_ in self.calls))))
        if method == 'turn/interrupt':
            self.finish('interrupted'); return {}
        raise AssertionError(method)
    def finish(self, status):
        turn='turn-'+str(sum(k=='turn/start' for k,_ in self.calls))
        self.waiting.extend([
            dict(method='item/completed',params=dict(threadId='thread-1',turnId=turn,item=dict(type='agentMessage',text='Synthetic engineering result.'))),
            dict(method='turn/completed',params=dict(threadId='thread-1',turn=dict(id=turn,status=status)))])
    def events(self): result,self.waiting=self.waiting,[]; return result
    def close(self): self.closed=True


@pytest.fixture
def policy(tmp_path):
    return dict(contract='codex-runtime-policy.v1',organization_id=uid(1),app_user_id=uid(2),
        execution_authorized=True,execution_authority_reference='synthetic fixture only; no provider calls',
        binary=str(tmp_path/'synthetic-codex'),cwd=str(tmp_path),sandbox='read-only',issues={uid(3):dict(
            project_id='prj_'+'1'*32,work_id='wrk_'+'2'*32,plan_id='SHRR-03',work_revision_sha256='3'*64,
            architecture_version=4,architecture_sha256='4'*64)})


@pytest.fixture
def runtime(tmp_path, policy):
    client=Client(); runtime=m.Runtime(tmp_path/'state',policy,create=True,client_factory=lambda *args:client)
    yield runtime,client
    runtime.close()


def request(policy, number=4, session=5):
    return dict(contract='codex-dispatch.v1',dispatch_id=uid(number),organization_id=policy['organization_id'],
        app_user_id=policy['app_user_id'],session_id=uid(session),issue_id=uid(3),message='Synthetic direct operator request.',
        binding=copy.deepcopy(policy['issues'][uid(3)]))


def test_dispatch_ack_and_exact_replay_never_start_second_turn(runtime,policy):
    value,client=runtime; req=request(policy)
    first=value.dispatch(req)
    assert first['state']=='running' and first['thread']=='thread-1'
    assert value.dispatch(req)==first
    assert len([k for k,_ in client.calls if k=='turn/start'])==1
    req['message']='changed'
    with pytest.raises(ValueError,match='identity changed'): value.dispatch(req)
    client.finish('completed'); assert value.status(uid(4))['result']=='Synthetic engineering result.'
    value.dispatch(request(policy,6))
    assert client.calls[-2][0]=='thread/resume'
    assert client.calls[-2][1]['sandbox']=='read-only'
    assert client.calls[-2][1]['cwd']==policy['cwd']
    assert 'Pinned engineering context' in client.calls[-1][1]['input'][0]['text']


@pytest.mark.parametrize('field',['organization_id','app_user_id','issue_id','binding','command','message'])
def test_wrong_context_and_worker_selected_commands_never_dispatch(runtime,policy,field):
    value,client=runtime; req=request(policy)
    if field=='binding': req[field]['architecture_sha256']='9'*64
    elif field=='command': req[field]='arbitrary command'
    elif field=='message': req[field]='x'*(m.MAX_MESSAGE+1)
    else: req[field]=uid(99)
    with pytest.raises(ValueError):value.dispatch(req)
    assert client.calls==[]


def test_execution_authority_cannot_come_from_webhook(tmp_path,policy):
    policy['execution_authorized']=False; client=Client()
    value=m.Runtime(tmp_path/'disabled',policy,create=True,client_factory=lambda *a:client)
    with pytest.raises(ValueError,match='not authorized'):value.dispatch(request(policy))
    assert client.calls==[]
    value.close()


def test_one_issue_executor_across_sessions_and_real_turn_interrupt(runtime,policy):
    value,client=runtime; value.dispatch(request(policy))
    with pytest.raises(ValueError,match='active or uncertain'): value.dispatch(request(policy,6,7))
    assert value.interrupt(uid(4))['state']=='interrupted'
    assert client.calls[-1]==('turn/interrupt',dict(threadId='thread-1',turnId='turn-1'))
    assert value.interrupt(uid(4))['state']=='interrupted'


def test_lost_dispatch_response_survives_restart_and_prevents_rerun(runtime,policy):
    value,client=runtime; client.fail='turn/start'
    with pytest.raises(ValueError,match='uncertain'):value.dispatch(request(policy))
    assert value.status(uid(4))['state']=='uncertain'
    assert value.dispatch(request(policy))['state']=='uncertain'
    value.close()
    other=Client(); restarted=m.Runtime(value.root,policy,client_factory=lambda *a:other)
    assert restarted.dispatch(request(policy))['state']=='uncertain'
    assert not other.calls
    with pytest.raises(ValueError,match='active or uncertain'):restarted.dispatch(request(policy,6))
    with pytest.raises(ValueError):restarted.interrupt(uid(4))
    restarted.close()


def test_completion_arriving_before_rpc_response_is_retained(runtime,policy):
    value,client=runtime; client.complete=True
    assert value.dispatch(request(policy))['state']=='completed'


def test_restart_does_not_claim_a_running_turn_finished(runtime,policy):
    value,client=runtime;value.dispatch(request(policy));value.close()
    restarted=m.Runtime(value.root,policy,client_factory=Client)
    assert restarted.status(uid(4))['state']=='uncertain'
    assert restarted.client is None
    restarted.close()


def test_journal_policy_and_privacy_cannot_be_changed(runtime,policy):
    value,_=runtime
    changed=copy.deepcopy(policy);changed['app_user_id']=uid(88)
    with pytest.raises(ValueError,match='policy differs'):m.Runtime(value.root,changed)
    value.path.chmod(0o644)
    with pytest.raises(ValueError,match='private'):m.Runtime(value.root,policy)
    value.path.chmod(0o600)


def test_private_http_auth_context_and_interrupt(runtime,policy):
    value,client=runtime; http=module('codex_runtime_http')
    server=http.server(value,b'synthetic-bridge-credential-32-bytes',('127.0.0.1',0))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base='http://127.0.0.1:'+str(server.server_port)
    def send(path,body=None,auth=True):
        headers={'Content-Type':'application/json'}
        if auth:headers['Authorization']='Bearer synthetic-bridge-credential-32-bytes'
        req=urllib.request.Request(base+path,data=None if body is None else m.encoded(body),headers=headers)
        return urllib.request.urlopen(req,timeout=3)
    try:
        with pytest.raises(urllib.error.HTTPError) as e:send('/v1/dispatch',request(policy),False)
        assert e.value.code==403 and not client.calls
        response=send('/v1/dispatch',request(policy));assert response.status==202
        assert json.load(send('/v1/runs/'+uid(4)))['state']=='running'
        assert json.load(send('/v1/interrupt',dict(dispatch_id=uid(4))))['state']=='interrupted'
        with pytest.raises(urllib.error.HTTPError):send('/v1/dispatch?untrusted=1',request(policy,6))
    finally:server.shutdown();server.server_close();thread.join(3)


def test_real_stdio_rpc_with_model_free_executable(tmp_path):
    executable=tmp_path/'fake-codex'
    executable.write_text('''#!/usr/bin/env python3
import json,sys
for line in sys.stdin:
 v=json.loads(line)
 if 'id' not in v: continue
 if v['method']=='initialize': result={'userAgent':'synthetic'}
 else:
  print(json.dumps({'method':'synthetic/event','params':{}}),flush=True)
  result={'thread':{'id':'synthetic-thread'}}
 print(json.dumps({'id':v['id'],'result':result}),flush=True)
''')
    executable.chmod(0o700)
    client=m.AppServer(str(executable),str(tmp_path),timeout=3)
    try:
        assert client.call('thread/start',{})['thread']['id']=='synthetic-thread'
        assert client.events()[0]['method']=='synthetic/event'
    finally:client.close()


def test_second_process_cannot_own_same_journal(runtime,policy):
    value,_=runtime
    with pytest.raises(ValueError,match='another adapter'):m.Runtime(value.root,policy)


def test_different_issues_cannot_edit_same_fixed_worktree(tmp_path,policy):
    policy['issues'][uid(30)]=dict(policy['issues'][uid(3)],work_id='wrk_'+'9'*32,plan_id='SHRR-04')
    client=Client();value=m.Runtime(tmp_path/'workspace',policy,create=True,client_factory=lambda *a:client)
    try:
        value.dispatch(request(policy))
        other=request(policy,6,7);other['issue_id']=uid(30);other['binding']=policy['issues'][uid(30)]
        with pytest.raises(ValueError,match='workspace has an active'):value.dispatch(other)
        assert len([m for m,_ in client.calls if m=='turn/start'])==1
    finally:value.close()
