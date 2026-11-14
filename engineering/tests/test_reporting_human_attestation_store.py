"""Disposable attestations require a real signed fixture Access identity."""
import importlib.util
from pathlib import Path
import sqlite3
import pytest
from test_history_web import key,access,headers,token,claims,ORIGIN
from test_reporting_onboarding_drafts import setup_draft,store,projects,uid,REPO
from test_reporting_onboarding_linear_decision import module as linear_decision,fixture_values

path=Path(__file__).resolve().parents[1]/'tools/rras_reporting/onboarding_human_attestation_store.py'
spec=importlib.util.spec_from_file_location('human_attestation_store_test',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
STATEMENT='I confirm I personally authored this exact Linear approval.'


def fixture(tmp_path,setup_draft,key):
    writer,history,origin,data=setup_draft;draft=writer.save(1234,object(),data)
    review,response=fixture_values(history,draft);connection=lambda:sqlite3.connect(tmp_path/'attest.sqlite3')
    with connection() as db:module.Store.initialize(db)
    reader=lambda _:response
    # Validates native content, project and author without treating it as proof
    # of authorship. Only the separately authenticated operator supplies that.
    source=linear_decision.Verifier(reader,lambda _:review,lambda *_:True,uid(1),uid(9),[uid(5)])
    tick=[1.0]
    service=module.Store(connection,access(key),reader,lambda _:review,source.verify,lambda:tick[0])
    allowed=headers(token(key))+[(b'origin',ORIGIN.encode())]
    return service,allowed,review,response,tick


def test_signed_operator_attests_exact_source_and_replay_is_denied(tmp_path,setup_draft,key):
    service,allowed,review,response,tick=fixture(tmp_path,setup_draft,key)
    assert not service.verify_authorship(response['comment'],review)
    offered=service.begin(allowed,uid(10),uid(8))
    assert offered['source_text']==response['comment']['body'] and offered['markdown_sha256']==review['markdown_sha256']
    result=service.confirm(allowed,offered['challenge'],STATEMENT)
    assert result['attested'] and not result['execution_authorized'] and service.verify_authorship(response['comment'],review)
    with pytest.raises(ValueError):service.confirm(allowed,offered['challenge'],STATEMENT)
    response['comment']['body']='changed'
    assert not service.verify_authorship(response['comment'],review)


@pytest.mark.parametrize('change',['missing_origin','bad_origin','wrong_user','bad_statement','expired','changed_source'])
def test_rejects_unauthenticated_stale_or_changed_attestations(tmp_path,setup_draft,key,change):
    service,allowed,review,response,tick=fixture(tmp_path,setup_draft,key)
    if change=='missing_origin':
        with pytest.raises(ValueError):service.begin(allowed[:-1],uid(10),uid(8))
        return
    if change=='bad_origin':
        with pytest.raises(ValueError):service.begin(allowed[:-1]+[(b'origin',b'https://wrong.test')],uid(10),uid(8))
        return
    offered=service.begin(allowed,uid(10),uid(8));statement=STATEMENT
    if change=='wrong_user':allowed=headers(token(key,claims(email='other@example.test')))+[(b'origin',ORIGIN.encode())]
    elif change=='bad_statement':statement='yes'
    elif change=='expired':tick[0]=400
    else:response['comment']['body']='changed'
    with pytest.raises(ValueError):service.confirm(allowed,offered['challenge'],statement)
    assert not service.verify_authorship(response['comment'],review)


def test_attestation_enables_only_exact_retained_review(setup_draft,tmp_path,key):
    from test_reporting_onboarding_decisions import decisions,OperatorStore
    from test_reporting_onboarding_review_store import reviews
    writer,history,origin,data=setup_draft;draft=writer.save(1234,object(),data)
    review_db=tmp_path/'reviews.sqlite3';attest_db=tmp_path/'attests.sqlite3'
    review_connection=lambda:sqlite3.connect(review_db);attest_connection=lambda:sqlite3.connect(attest_db)
    with review_connection() as db:reviews.ReviewStore.initialize(db)
    with attest_connection() as db:module.Store.initialize(db)
    class History:
        def project(self,scope,pid):return history.project(scope,pid)
        def architecture(self,scope,pid,version):return history.projects.read(scope,dict(view='architecture',project_id=pid,version=version))['document']
    issue=lambda identifier:dict(organization_id=uid(1),team_id=uid(2),project_id=uid(3),id=identifier)
    registry=reviews.ReviewStore(review_connection,History(),issue,[REPO]);review_id=registry.prepare(origin,uid(7),1)
    comment=dict(id=uid(8),author_id=uid(5),author_is_app=False,issue_id=uid(7),team_id=uid(2),project_id=uid(3),
        body=f"I approve architecture version 1 sha256 {draft['markdown_sha256']}",created_at='2026-11-12T12:00:00Z',
        edited_at=None,bot_actor=None,external_user=None,on_behalf_of=None,archived_at=None)
    native=lambda _:dict(viewer_id=uid(9),organization_id=uid(1),comment=comment)
    preliminary=linear_decision.Verifier(native,registry.read,lambda *_:True,uid(1),uid(9),[uid(5)])
    attests=module.Store(attest_connection,access(key),native,registry.read,preliminary.verify)
    verified=linear_decision.Verifier(native,registry.read,attests.verify_authorship,uid(1),uid(9),[uid(5)])
    recorder=decisions.DecisionRecorder(verified.verify,OperatorStore(history),[REPO]);request=dict(review_id=review_id,comment_id=uid(8))
    with pytest.raises(ValueError,match='independent direct human authorship'):recorder.approve(request)
    allowed=headers(token(key))+[(b'origin',ORIGIN.encode())]
    challenge=attests.begin(allowed,review_id,uid(8));attests.confirm(allowed,challenge['challenge'],STATEMENT)
    approved=recorder.approve(request)
    assert approved['version']==1 and not approved['execution_authorized']
    assert history.project(REPO,draft['project_id'])['governing_version']==1
