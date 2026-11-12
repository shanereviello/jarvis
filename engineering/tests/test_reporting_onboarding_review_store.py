import importlib.util
from pathlib import Path
import sqlite3
import pytest
from test_reporting_onboarding_drafts import setup_draft,store,projects,uid,REPO
from test_reporting_onboarding_decisions import decisions,OperatorStore
from test_reporting_onboarding_linear_decision import module as linear_decision

path=Path(__file__).resolve().parents[1]/'tools/rras_reporting/onboarding_review_store.py'
spec=importlib.util.spec_from_file_location('review_store_fixture',path)
reviews=importlib.util.module_from_spec(spec);spec.loader.exec_module(reviews)


def test_review_pins_exact_retained_document_and_decision(tmp_path,setup_draft):
    writer,fixture,origin,data=setup_draft;draft=writer.save(1234,object(),data)
    dbpath=tmp_path/'review.sqlite3'
    connection=lambda:sqlite3.connect(dbpath)
    with connection() as db:reviews.ReviewStore.initialize(db)
    class History:
        def project(self,scope,pid):return fixture.project(scope,pid)
        def architecture(self,scope,pid,version):return fixture.projects.read(scope,dict(view='architecture',project_id=pid,version=version))['document']
    issue=lambda identifier:dict(organization_id=uid(1),team_id=uid(2),project_id=uid(3),id=identifier)
    registry=reviews.ReviewStore(connection,History(),issue,[REPO])
    review_id=registry.prepare(origin,uid(7),1)
    assert registry.prepare(origin,uid(7),1)==review_id
    assert registry.read(review_id)['markdown_sha256']==draft['markdown_sha256']
    with connection() as db:
        with pytest.raises(sqlite3.IntegrityError):db.execute("DELETE FROM architecture_reviews")
    comment=dict(id=uid(8),author_id=uid(5),author_is_app=False,issue_id=uid(7),team_id=uid(2),project_id=uid(3),
        body=f"I approve architecture version 1 sha256 {draft['markdown_sha256']}",created_at='2026-11-12T12:00:00Z',
        edited_at=None,bot_actor=None,external_user=None,on_behalf_of=None,archived_at=None)
    reader=lambda _:dict(viewer_id=uid(9),organization_id=uid(1),comment=comment)
    verifier=linear_decision.Verifier(reader,registry.read,uid(1),uid(9),[uid(5)])
    approved=decisions.DecisionRecorder(verifier.verify,OperatorStore(fixture),[REPO]).approve(dict(comment_id=uid(8),review_id=review_id))
    assert approved['version']==1 and not approved['execution_authorized']
    assert fixture.project(REPO,draft['project_id'])['governing_version']==1
    with pytest.raises(ValueError):registry.read(uid(99))


def test_wrong_issue_and_tampered_document_do_not_create_review(tmp_path,setup_draft):
    writer,fixture,origin,data=setup_draft;draft=writer.save(1234,object(),data)
    connection=lambda:sqlite3.connect(tmp_path/'reviews.sqlite3')
    with connection() as db:reviews.ReviewStore.initialize(db)
    class History:
        def project(self,scope,pid):return fixture.project(scope,pid)
        def architecture(self,scope,pid,version):return {'markdown':'different bytes'}
    wrong=lambda identifier:dict(organization_id=uid(1),team_id=uid(2),project_id=uid(99),id=identifier)
    with pytest.raises(ValueError):reviews.ReviewStore(connection,History(),wrong,[REPO]).prepare(origin,uid(7),1)
    right=lambda identifier:dict(organization_id=uid(1),team_id=uid(2),project_id=uid(3),id=identifier)
    with pytest.raises(ValueError):reviews.ReviewStore(connection,History(),right,[REPO]).prepare(origin,uid(7),1)
    with connection() as db:assert db.execute('SELECT count(*) FROM architecture_reviews').fetchone()[0]==0
