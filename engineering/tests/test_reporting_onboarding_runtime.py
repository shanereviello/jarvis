from contextlib import contextmanager
import importlib.util
from pathlib import Path
import sqlite3
import pytest

path=Path(__file__).resolve().parents[1]/'tools/rras_reporting/onboarding_runtime.py'
spec=importlib.util.spec_from_file_location('planning_runtime_fixture',path)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def uid(n):return f'00000000-0000-4000-8000-{n:012d}'


@pytest.fixture
def runtime(tmp_path):
    @contextmanager
    def connect():
        db=sqlite3.connect(tmp_path/'planning.sqlite3')
        try:yield db
        finally:db.close()
    with connect() as db:m.Runtime.initialize(db)
    class Registry:
        def __init__(self):self.active=set()
        def register(self,peer,dispatch,expires):self.active.add(dispatch)
        def revoke(self,dispatch):self.active.discard(dispatch)
    class Launch:
        def parameters(self,dispatch):return {'config':{'mcp_servers':{'engineering_planning':{'dispatch':dispatch}}}}
        def verify_inventory(self,client,thread):return True
    class Client:
        def __init__(self):self.calls=[];self.fail=False;self.pending=[]
        def call(self,method,arguments):
            self.calls.append((method,arguments))
            if self.fail:raise OSError('fixture failure')
            if method in ('thread/start','thread/resume'):return {'thread':{'id':'thread-fixture','cwd':str(tmp_path)}}
            return {'turn':{'id':'turn-fixture'}}
        def events(self):out,self.pending=self.pending,[];return out
    client=Client();registry=Registry()
    policy=dict(organization_id=uid(1),app_user_id=uid(2),peer_uid=1000,cwd=str(tmp_path),
        planning_authorized=True,authority_reference='fixture only')
    value=m.Runtime(connect,policy,lambda _:True,registry,Launch(),lambda:client,lambda:100,tmp_path/'planning.lock')
    event=dict(dispatch_id=uid(3),session_id=uid(4),issue_id=uid(5),organization_id=uid(1),app_user_id=uid(2),message='Plan this project')
    yield value,event,client,registry
    value.close()


def test_planning_turn_is_read_only_and_exact_replay_does_not_restart(runtime):
    value,event,client,registry=runtime
    first=value.dispatch(event);assert first['state']=='running'
    assert client.calls[0][1]['sandbox']=='read-only'
    assert client.calls[0][1]['approvalPolicy']=='never'
    assert len(client.calls)==2 and value.dispatch(event)['replayed'] and len(client.calls)==2
    value.complete(event['dispatch_id'],'thread-fixture','turn-fixture','completed','Draft prepared')
    assert not registry.active


def test_uncertain_turn_is_never_automatically_rerun(runtime):
    value,event,client,registry=runtime;client.fail=True
    with pytest.raises(ValueError,match='uncertain'):value.dispatch(event)
    assert value.dispatch(event)['state']=='uncertain' and len(client.calls)==1
    assert not registry.active


def test_unverified_or_unpaid_planning_never_starts(runtime):
    value,event,client,registry=runtime;value.verify_event=lambda _:False
    with pytest.raises(ValueError):value.dispatch(event)
    assert client.calls==[]
    value.verify_event=lambda _:True;value.policy['planning_authorized']=False
    with pytest.raises(ValueError):value.dispatch(event)
    assert client.calls==[]


def test_restart_preserves_uncertainty_without_relaunch(runtime):
    value,event,client,registry=runtime
    value.dispatch(event)
    assert value.recover_after_exclusive_start()=={'uncertain':1,'automatically_retried':0}
    assert value.dispatch(event)['state']=='uncertain'
    assert len(client.calls)==2 and not registry.active


def test_active_or_uncertain_turn_blocks_another_dispatch(runtime):
    value,event,client,registry=runtime
    value.dispatch(event)
    with pytest.raises(sqlite3.IntegrityError):value.dispatch(dict(event,dispatch_id=uid(9)))
    assert len(client.calls)==2


def test_interrupt_requires_same_session_and_waits_for_native_terminal_event(runtime):
    value,event,client,registry=runtime;value.dispatch(event)
    with pytest.raises(ValueError):value.interrupt(event['dispatch_id'],uid(99))
    assert value.interrupt(event['dispatch_id'],event['session_id'])['state']=='interrupt_requested'
    assert client.calls[-1][0]=='turn/interrupt'
    value.complete(event['dispatch_id'],'thread-fixture','turn-fixture','interrupted')
    assert not registry.active


def test_followup_resumes_same_thread_and_issue(runtime):
    value,event,client,registry=runtime;value.dispatch(event)
    value.complete(event['dispatch_id'],'thread-fixture','turn-fixture','completed')
    followup=dict(event,dispatch_id=uid(9),message='Refine the draft')
    assert value.dispatch(followup)['state']=='running'
    assert client.calls[-2][0]=='thread/resume'
    assert client.calls[-2][1]['threadId']=='thread-fixture'


def test_second_runtime_cannot_recover_or_launch_same_journal(runtime,tmp_path):
    value,event,client,registry=runtime
    with pytest.raises(ValueError,match='already owned'):
        m.Runtime(value.connection,value.policy,lambda _:True,registry,value.launch,lambda:client,lambda:100,tmp_path/'planning.lock')


def test_new_owner_recovers_running_turn_as_uncertain(runtime,tmp_path):
    value,event,client,registry=runtime;value.dispatch(event);value.close()
    reopened=m.Runtime(value.connection,value.policy,lambda _:True,registry,value.launch,lambda:client,lambda:100,tmp_path/'planning.lock')
    try:
        assert reopened.dispatch(event)['state']=='uncertain'
        assert len(client.calls)==2 and not registry.active
    finally:reopened.close()


def test_unexpected_tool_inventory_refuses_before_model_turn(runtime):
    value,event,client,registry=runtime
    value.launch.verify_inventory=lambda *_:False
    with pytest.raises(ValueError,match='uncertain'):value.dispatch(event)
    assert [name for name,_ in client.calls]==['thread/start']


def test_native_collector_ignores_reasoning_and_other_threads(runtime):
    value,event,client,registry=runtime;value.dispatch(event)
    def item(thread,channel,text):return dict(method='item/completed',params=dict(threadId=thread,turnId='turn-fixture',
        item=dict(type='agentMessage',channel=channel,text=text)))
    client.pending=[item('other','final','other content'),item('thread-fixture','analysis','private reasoning'),
        item('thread-fixture','final','Draft complete'),dict(method='turn/completed',params=dict(threadId='thread-fixture',
        turn=dict(id='turn-fixture',status='completed')))]
    assert value.collect(event['dispatch_id'])['state']=='completed'
    with value.connection() as db:
        assert db.execute('SELECT result FROM planning_turns').fetchone()[0]=='Draft complete'
    assert not registry.active
