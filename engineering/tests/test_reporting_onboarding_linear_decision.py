"""Native human comment verification is separate from model-supplied claims."""
import copy
import importlib.util
from pathlib import Path
import pytest
from test_reporting_onboarding_drafts import setup_draft,store,projects,uid,REPO
from test_reporting_onboarding_decisions import decisions,evidence_for,OperatorStore

path=Path(__file__).resolve().parents[1]/'tools/rras_reporting/onboarding_linear_decision.py'
spec=importlib.util.spec_from_file_location('linear_decision_test',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def fixture_values(fixture,draft):
    evidence=evidence_for(fixture,draft)
    review={k:evidence[k] for k in ('organization_id','linear_project_id','scope','project_id','document_id','version',
        'markdown_sha256','expected_governing_version','expected_project_head')}
    review.update(team_id=uid(6),issue_id=uid(7))
    comment=dict(id=uid(8),author_id=uid(5),author_is_app=False,issue_id=uid(7),team_id=uid(6),
        project_id=uid(3),body=f"I approve architecture version {draft['version']} sha256 {draft['markdown_sha256']}",
        created_at='2026-11-12T12:00:00Z',updated_at='2026-11-12T12:00:00Z')
    response=dict(viewer_id=uid(9),organization_id=uid(1),comment=comment)
    return review,response


def test_native_human_source_designates_exact_retained_version(setup_draft):
    writer,fixture,_,data=setup_draft;draft=writer.save(1234,object(),data)
    review,response=fixture_values(fixture,draft)
    verifier=module.Verifier(lambda _:response,lambda _:review,uid(1),uid(9),[uid(5)])
    result=decisions.DecisionRecorder(verifier.verify,OperatorStore(fixture),[REPO]).approve(dict(comment_id=uid(8),review_id=uid(10)))
    assert result['execution_authorized'] is False
    assert fixture.project(REPO,draft['project_id'])['governing_version']==1


@pytest.mark.parametrize('change',['edited','app','author','issue','project','org','viewer','digest','comment','extra'])
def test_reject_wrong_or_ambiguous_source(setup_draft,change):
    writer,fixture,_,data=setup_draft;draft=writer.save(1234,object(),data)
    review,response=fixture_values(fixture,draft);response=copy.deepcopy(response);c=response['comment']
    if change=='edited':c['updated_at']='2026-11-12T12:00:01Z'
    elif change=='app':c['author_is_app']=True
    elif change=='author':c['author_id']=uid(11)
    elif change=='issue':c['issue_id']=uid(11)
    elif change=='project':c['project_id']=uid(11)
    elif change=='org':response['organization_id']=uid(11)
    elif change=='viewer':response['viewer_id']=uid(11)
    elif change=='digest':c['body']=c['body'].replace(draft['markdown_sha256'],'0'*64)
    elif change=='comment':c['id']=uid(11)
    else:c['unexpected']=True
    verifier=module.Verifier(lambda _:response,lambda _:review,uid(1),uid(9),[uid(5)])
    with pytest.raises(ValueError):decisions.DecisionRecorder(verifier.verify,OperatorStore(fixture),[REPO]).approve(dict(comment_id=uid(8),review_id=uid(10)))
    assert fixture.project(REPO,draft['project_id'])['governing_version'] is None
