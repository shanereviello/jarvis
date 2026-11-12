"""Operator decisions are separate from agent draft-writing authority."""
import hashlib
import importlib.util
from pathlib import Path
import pytest
from test_reporting_onboarding_drafts import setup_draft,store,projects,uid,REPO
from test_history_reporting_contract import request
from test_history_projects import envelope

PATH=Path(__file__).resolve().parents[1]/'tools/rras_reporting/onboarding_decisions.py'
spec=importlib.util.spec_from_file_location('onboarding_decisions_fixture',PATH)
decisions=importlib.util.module_from_spec(spec);spec.loader.exec_module(decisions)


class OperatorStore:
    def __init__(self,fixture):self.fixture=fixture
    def project(self,scope,project_id):return self.fixture.project(scope,project_id)
    def observe_decision(self,value,decision_id):
        r=request('decision.observe');r.update(client_event_key='operator-decision:'+decision_id,
            scope=value['scope'],source=dict(kind='imported',namespace=value['source_namespace'],id=value['source_id']),
            context=dict(project_id=value['project_id'],architecture=dict(document_id=value['document_id'],
                version=value['version'],markdown_sha256=value['markdown_sha256']),work=None))
        r['body'].update(decision_id=decision_id,kind='architecture',state='approved',attribution='imported_source',
            attributed_author=dict(role='human',runtime='linear',source_actor_id=value['human_actor_id']),
            source_reference=dict(namespace=value['source_namespace'],id=value['source_id'],sha256=value['source_sha256']),
            decision_text=value['decision_text'])
        return self.fixture.reporting.submit(r,peer_uid=999)['receipt']['request_sha256']
    def designate(self,scope,project_id,head,version,digest,receipt):
        r=envelope(project_id,'architecture.designate',dict(version=version,markdown_sha256=digest,
            reason='Recorded exact operator decision receipt '+receipt),head,scope)
        r['client_event_key']='operator-designation:'+receipt
        return self.fixture.projects.submit(r,peer_uid=999)


def evidence_for(fixture,result):
    project=fixture.project(REPO,result['project_id']);message='I approve this exact architecture.'
    return dict(organization_id=uid(1),linear_project_id=uid(3),scope=REPO,project_id=result['project_id'],
        document_id=result['document_id'],version=result['version'],markdown_sha256=result['markdown_sha256'],
        expected_governing_version=project['governing_version'],expected_project_head=project['head'],
        human_actor_id=uid(5),source_id='fixture-comment-1',source_namespace='linear_comment',
        source_sha256=hashlib.sha256(message.encode()).hexdigest(),decision_text=message)


def test_verified_decision_and_designation_are_separate_and_replayable(setup_draft):
    writer,fixture,_,data=setup_draft;result=writer.save(1234,object(),data);source=evidence_for(fixture,result)
    recorder=decisions.DecisionRecorder(lambda evidence:source,OperatorStore(fixture),[REPO])
    approved=recorder.approve(object());assert approved['execution_authorized'] is False
    assert fixture.project(REPO,result['project_id'])['governing_version']==1
    assert recorder.approve(object())==approved
    with fixture.projects.store.connection() as db:
        observations=[r for r,_ in fixture.reporting.events(db) if r['operation']=='decision.observe']
    assert len(observations)==1 and observations[0]['body']['attributed_author']['role']=='human'


@pytest.mark.parametrize('change',['digest','source','scope','actor','stale'])
def test_changed_or_unverified_decisions_do_not_designate(setup_draft,change):
    writer,fixture,_,data=setup_draft;result=writer.save(1234,object(),data);source=evidence_for(fixture,result)
    if change=='digest':source['markdown_sha256']='0'*64
    elif change=='source':source['decision_text']='edited after verification'
    elif change=='scope':source['scope']={'kind':'repository','id':'other'}
    elif change=='actor':source['human_actor_id']='agent-written'
    else:source['expected_project_head']='0'*64
    recorder=decisions.DecisionRecorder(lambda evidence:source,OperatorStore(fixture),[REPO])
    with pytest.raises(ValueError):recorder.approve(object())
    assert fixture.project(REPO,result['project_id'])['governing_version'] is None


def test_verifier_refusal_cannot_be_replaced_by_agent_supplied_claim(setup_draft):
    writer,fixture,_,data=setup_draft;result=writer.save(1234,object(),data)
    def refuse(_):raise ValueError('not independently verified')
    recorder=decisions.DecisionRecorder(refuse,OperatorStore(fixture),[REPO])
    with pytest.raises(ValueError,match='not independently verified'):recorder.approve(evidence_for(fixture,result))
    assert fixture.project(REPO,result['project_id'])['governing_version'] is None


def test_later_version_requires_exact_reviewed_prior_head(setup_draft):
    writer,fixture,_,data=setup_draft;first=writer.save(1234,object(),data)
    first_source=evidence_for(fixture,first)
    decisions.DecisionRecorder(lambda evidence:first_source,OperatorStore(fixture),[REPO]).approve(object())
    project=fixture.project(REPO,first['project_id']);text='# Revised architecture\n\nPLAN-01 revised.\n'
    save=envelope(first['project_id'],'architecture.save',dict(document_id=first['document_id'],version=2,
        previous_sha256=first['markdown_sha256'],title='Revised architecture',change_summary='Fixture revision',
        markdown=text,source_reference='fixture'),project['head'])
    fixture.projects.submit(save)
    revised=dict(first,version=2,markdown_sha256=hashlib.sha256(text.encode()).hexdigest())
    source=evidence_for(fixture,revised);source['source_id']='fixture-comment-2'
    decisions.DecisionRecorder(lambda evidence:source,OperatorStore(fixture),[REPO]).approve(object())
    assert fixture.project(REPO,first['project_id'])['governing_version']==2
