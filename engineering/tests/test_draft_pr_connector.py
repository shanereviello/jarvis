"""One-use operator connector lifecycle; actual local Git, fake GitHub metadata."""
import copy
import json
from pathlib import Path
from unittest.mock import patch
import pytest
from test_workflow_finish import case
from test_workflow_publication import pubcase
import test_managed_events as managed

pytestmark=pytest.mark.parametrize('case',[{'publication_remote':'git@github.com:fixture/library.git'}],indirect=True)


@pytest.fixture
def bridge(pubcase):
    x=pubcase;m=managed.module('draft_pr_connector');hf=x.p.local('publication_handoff')
    hf.git(['clone','--quiet','--branch',x.proof['branch'],str(x.package/'review.bundle'),str(x.workspace/'repo')])
    hf.git(['-C',str(x.workspace/'repo'),'remote','remove','origin'])
    original=m.local
    with patch.object(m,'local',side_effect=lambda name:{'publication_handoff':hf,'workflow_publication':x.p,'approved_launch':x.c.x.l}.get(name) or original(name)):
        yield x,m


def branch(x):return {'branch':{'name':x.proof['branch'],'commit':{'sha':x.proof['commit']}},'prs':[]}
def response(x):return {'url':x.pr['url'],'number':7,'head':x.proof['branch'],'head_sha':x.proof['commit'],'head_repo_full_name':'fixture/library','base':'main','draft':True,'merged':False,'state':'open'}


def test_exact_connector_intent_arm_and_normalized_receipt(bridge):
    x,m=bridge;intent=m.prepare(x.package,x.workspace)
    assert intent['create']['draft'] is True and intent['create']['repository_full_name']=='fixture/library'
    assert intent['create']['head']==x.proof['branch'] and intent['create']['base']=='main'
    assert '%2F' in intent['branch_read']['url'] and 'state=all' in intent['prs_read']['url']
    armed=m.arm(x.package,x.workspace,branch(x));assert armed['create']==intent['create']
    result=m.complete(x.package,x.workspace,response(x));assert result['status']=='draft_created'
    assert json.loads((x.workspace/'draft-pr-receipt.json').read_bytes())==x.pr
    assert (x.workspace/'draft-pr-armed.json').stat().st_mode&0o777==0o600
    with pytest.raises(ValueError):m.prepare(x.package,x.workspace)


def test_lost_connector_response_keeps_unknown_and_no_second_creation(bridge):
    x,m=bridge;m.prepare(x.package,x.workspace);m.arm(x.package,x.workspace,branch(x))
    assert m.unknown(x.package,x.workspace)['status']=='unknown'
    with pytest.raises(ValueError):m.prepare(x.package,x.workspace)
    with pytest.raises(ValueError):m.arm(x.package,x.workspace,branch(x))
    assert not (x.workspace/'draft-pr-receipt.json').exists()


def test_arm_reply_loss_already_consumes_fence(bridge):
    x,m=bridge;m.prepare(x.package,x.workspace);m.arm(x.package,x.workspace,branch(x))
    with pytest.raises(FileExistsError):m.arm(x.package,x.workspace,branch(x))
    with pytest.raises(ValueError):m.prepare(x.package,x.workspace)


@pytest.mark.parametrize('kind',['changed_commit','changed_branch','existing_pr'])
def test_remote_preflight_refuses_before_arming(bridge,kind):
    x,m=bridge;m.prepare(x.package,x.workspace);data=branch(x)
    if kind=='changed_commit':data['branch']['commit']['sha']='0'*40
    if kind=='changed_branch':data['branch']['name']='main'
    if kind=='existing_pr':data['prs']=[{'number':4}]
    with pytest.raises(ValueError):m.arm(x.package,x.workspace,data)
    assert not (x.workspace/'draft-pr-armed.json').exists()


@pytest.mark.parametrize('field,value',[('head_sha','0'*40),('base','other'),('draft',False),('merged',True),('number',True),('url','https://github.com/other/repo/pull/7')])
def test_response_drift_is_unknown_without_valid_pr_receipt(bridge,field,value):
    x,m=bridge;m.prepare(x.package,x.workspace);m.arm(x.package,x.workspace,branch(x));data=response(x);data[field]=value
    assert m.complete(x.package,x.workspace,data)['status']=='unknown'
    assert not (x.workspace/'draft-pr-receipt.json').exists()


def test_rest_shape_normalizes_without_sdk_field_assumptions(bridge):
    x,m=bridge;raw={'html_url':x.pr['url'],'number':7,'head':{'ref':x.proof['branch'],'sha':x.proof['commit'],'repo':{'full_name':'fixture/library'}},'base':{'ref':'main'},'draft':True,'merged':False,'state':'open'}
    assert m.normalize(x.proof,raw)==x.pr


def test_changed_local_checkout_blocks_intent(bridge):
    x,m=bridge;(x.workspace/'repo/src/library.py').write_text('changed')
    with pytest.raises(ValueError):m.prepare(x.package,x.workspace)
    assert not (x.workspace/'draft-pr-intent.json').exists()


def test_intent_tampering_blocks_arm(bridge):
    x,m=bridge;m.prepare(x.package,x.workspace);(x.workspace/'draft-pr-intent.json').write_bytes(b'{}')
    with pytest.raises(ValueError):m.arm(x.package,x.workspace,branch(x))


def test_cannot_complete_before_fence(bridge):
    x,m=bridge;m.prepare(x.package,x.workspace)
    with pytest.raises(OSError):m.complete(x.package,x.workspace,response(x))


def test_connector_receipt_flows_to_protected_publication_journal(bridge):
    x,m=bridge;m.prepare(x.package,x.workspace);m.arm(x.package,x.workspace,branch(x));m.complete(x.package,x.workspace,response(x))
    x.pr_path.write_bytes((x.workspace/'draft-pr-receipt.json').read_bytes())
    out=x.root/'final-custody';x.capture(out);result=x.record(out)
    assert result['draft_pr_recorded'] and result['provenance']=='imported'


def test_raced_response_keeps_candidate_for_read_only_inspection(bridge):
    x,m=bridge;m.prepare(x.package,x.workspace);m.arm(x.package,x.workspace,branch(x));raw=response(x);raw['head_sha']='0'*40
    result=m.complete(x.package,x.workspace,raw)
    assert result['status']=='unknown' and result['candidate_for_inspection']=={'number':7,'url':x.pr['url']}


def test_malformed_branch_commit_shape_is_refused_before_fence(bridge):
    x,m=bridge;m.prepare(x.package,x.workspace);data=branch(x);data['branch']['commit']='bad'
    with pytest.raises(ValueError):m.arm(x.package,x.workspace,data)
    assert not (x.workspace/'draft-pr-armed.json').exists()


def test_worker_identity_cannot_prepare_connector_request(bridge):
    x,m=bridge
    with patch.object(m.os,'getuid',return_value=996),pytest.raises(ValueError):m.prepare(x.package,x.workspace)
    assert not (x.workspace/'draft-pr-intent.json').exists()


def test_unknown_branch_publication_cannot_prepare_pr_creation(bridge):
    x,m=bridge;report=dict(x.transport,status='unknown',error_type='TimeoutError')
    (x.workspace/'publication-receipt.json').write_bytes(x.c.x.a.encoded(report))
    with pytest.raises(ValueError):m.prepare(x.package,x.workspace)
    assert not (x.workspace/'draft-pr-intent.json').exists()


def test_operator_cli_emits_versioned_binding_protocol(bridge,monkeypatch,capsys):
    import sys
    x,m=bridge
    monkeypatch.setattr(sys,'argv',['draft-pr.py','prepare','--package',str(x.package),'--workspace',str(x.workspace)])
    m.main();reply=json.loads(capsys.readouterr().out)
    assert reply['operator_binding_protocol']==1 and reply['create']['draft'] is True
