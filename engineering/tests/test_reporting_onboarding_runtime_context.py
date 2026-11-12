import importlib.util
from pathlib import Path
import pytest
from test_reporting_onboarding_runtime import runtime,uid

path=Path(__file__).resolve().parents[1]/'tools/rras_reporting/onboarding_runtime_context.py'
spec=importlib.util.spec_from_file_location('planning_runtime_context_fixture',path)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_native_context_requires_exact_active_retained_dispatch(runtime):
    value,event,client,registry=runtime
    origin=dict(organization_id=uid(1),source_session=uid(4),agent='codex')
    class Reader:
        def origin(self,dispatch,issue,*,message,session):
            if (dispatch,issue)!=(event['dispatch_id'],event['issue_id']):raise ValueError('wrong event')
            if message!=event['message'] or session!=event['session_id']:raise ValueError('wrong source')
            return origin
    context=m.Context(value.connection,Reader(),uid(1),uid(2),1000)
    assert context.verify_event(event)
    assert not context.active(1000,event['dispatch_id'])
    value.dispatch(event)
    assert context.active(1000,event['dispatch_id'])
    assert not context.active(999,event['dispatch_id'])
    assert context.native(event['dispatch_id'])==origin
    value.complete(event['dispatch_id'],'thread-fixture','turn-fixture','completed')
    with pytest.raises(ValueError):context.native(event['dispatch_id'])


def test_stop_must_match_verified_human_signal_and_active_session(runtime):
    value,event,client,registry=runtime;value.dispatch(event)
    class Reader:
        def origin(self,dispatch,issue,*,message,session,stop=False):
            if (dispatch,issue,message,session,stop)!=(uid(9),event['issue_id'],'Stop',event['session_id'],True):
                raise ValueError('not a verified stop')
            return dict(organization_id=uid(1),source_session=event['session_id'],agent='codex')
    context=m.Context(value.connection,Reader(),uid(1),uid(2),1000)
    stop=dict(stop_dispatch_id=uid(9),target_dispatch_id=event['dispatch_id'],session_id=event['session_id'],
        issue_id=event['issue_id'],organization_id=uid(1),app_user_id=uid(2),message='Stop')
    assert context.verify_stop(stop)
    assert not context.verify_stop(dict(stop,target_dispatch_id=uid(10)))
