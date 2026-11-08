"""Native handoffs preserve app identities and do not guess uncertain delivery."""
import copy
import importlib.util
from pathlib import Path
import uuid
import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('native_handoff_test',ROOT/'tools/rras_reporting/native_handoff.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
uid=lambda number:str(uuid.UUID(int=number))


def fixture(role='jarvis'):
    pin=dict(project_id='prj_'+'1'*32,work_id='wrk_'+'2'*32,plan_id='SHRR-03',work_revision_sha256='3'*64,
        architecture_version=4,architecture_sha256='4'*64)
    policy=dict(contract='native-agent-handoff-policy.v1',organization_id=uid(1),agents=dict(jarvis=uid(20),codex=uid(2)),issues={uid(4):pin})
    context=dict(session_id=uid(5),issue_id=uid(4),binding=pin,parent_handoff_id=None,depth=0)
    arguments=dict(key='investigate-failure',summary='Observed failure; api_key=sk-fixture-DO-NOT-RETAIN-123456789',
        requested_action='Investigate and report evidence.',references=[dict(namespace='validation',id='fixture-failure',sha256='a'*64)],
        limitations=['No execution or architecture approval is inferred.'])
    return policy,context,arguments,m.prepare(policy,role,context,arguments)


@pytest.mark.parametrize('role',['jarvis','codex'])
def test_handoff_freezes_actual_source_target_work_and_redacts_prose(role):
    policy,context,args,intent=fixture(role)
    assert intent==m.prepare(policy,role,context,args)
    assert intent['sender_app_user_id']==policy['agents'][role]
    assert intent['recipient_app_user_id']!=intent['sender_app_user_id']
    assert intent['binding']==context['binding'] and uuid.UUID(intent['comment_id']).version==4
    assert not intent['execution_authority_granted'] and not intent['human_approval_inferred']
    assert b'sk-fixture-DO-NOT-RETAIN' not in m.encoded(intent)
    assert 'createAsUser' not in m.mutation(intent,'comment')['variables']['input']
    assert m.mutation(intent,'session')['variables']['input']==dict(commentId=intent['comment_id'])


@pytest.mark.parametrize('change',['work','agent','depth','caller_context'])
def test_work_role_and_chain_cannot_be_selected_by_tool_prose(change):
    policy,context,args,_=fixture()
    if change=='work':context['binding']=dict(context['binding'],work_id='wrk_'+'9'*32)
    if change=='agent':policy['agents']['codex']=policy['agents']['jarvis']
    if change=='depth':context['depth']=4
    if change=='caller_context':args['issue_id']=uid(99)
    with pytest.raises(ValueError):m.prepare(policy,'jarvis',context,args)


def comment_response(intent,sessions=None):
    return dict(statusCode=200,body=dict(data=dict(comment=dict(id=intent['comment_id'],body=m.comment_body(intent),
        user=dict(id=intent['sender_app_user_id']),issue=dict(id=intent['issue_id']),
        agentSessions=dict(nodes=[] if sessions is None else sessions,pageInfo=dict(hasNextPage=False,endCursor=None))))))


def test_lost_native_session_mutation_reconciles_one_exact_comment_and_recipient():
    _,_,_,intent=fixture();target=dict(id=uid(60),appUser=dict(id=intent['recipient_app_user_id']),issue=dict(id=intent['issue_id']))
    reply=comment_response(intent,[target]);assert m.reconcile_session(intent,reply)==uid(60)
    for changed in (comment_response(intent,[]),comment_response(intent,[target,target])):
        with pytest.raises(ValueError):m.reconcile_session(intent,changed)
    reply['body']['data']['comment']['user']['id']=uid(99)
    with pytest.raises(ValueError):m.reconcile_session(intent,reply)


def test_native_event_correlates_exact_app_comment_issue_without_human_creator():
    _,_,_,intent=fixture();event=dict(type='AgentSessionEvent',action='created',organizationId=intent['organization_id'],
        appUserId=intent['recipient_app_user_id'],agentSession=dict(id=uid(60),issueId=intent['issue_id'],
            creatorId=None,sourceCommentId=intent['comment_id']))
    assert m.correlate(intent,event)==uid(60)
    for key in ('sourceCommentId','issueId'):
        wrong=copy.deepcopy(event);wrong['agentSession'][key]=uid(99)
        with pytest.raises(ValueError):m.correlate(intent,wrong)
    wrong=copy.deepcopy(event);wrong['appUserId']=intent['sender_app_user_id']
    with pytest.raises(ValueError):m.correlate(intent,wrong)


def test_handoff_prose_cannot_add_an_automatic_mention_or_markdown_link():
    policy,context,args,_=fixture();args['summary']='@Codex [run](https://linear.app/user) ``` end'
    body=m.comment_body(m.prepare(policy,'jarvis',context,args))
    assert '@Codex' not in body and '[run](' not in body
