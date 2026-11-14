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
        created_at='2026-11-12T12:00:00Z',edited_at=None,bot_actor=None,external_user=None,on_behalf_of=None,archived_at=None)
    response=dict(viewer_id=uid(9),organization_id=uid(1),comment=comment)
    return review,response


def test_native_human_source_designates_exact_retained_version(setup_draft):
    writer,fixture,_,data=setup_draft;draft=writer.save(1234,object(),data)
    review,response=fixture_values(fixture,draft)
    verifier=module.Verifier(lambda _:response,lambda _:review,lambda *_:True,uid(1),uid(9),[uid(5)])
    result=decisions.DecisionRecorder(verifier.verify,OperatorStore(fixture),[REPO]).approve(dict(comment_id=uid(8),review_id=uid(10)))
    assert result['execution_authorized'] is False
    assert fixture.project(REPO,draft['project_id'])['governing_version']==1


def test_linear_author_fields_alone_do_not_prove_direct_human_approval(setup_draft):
    writer,fixture,_,data=setup_draft;draft=writer.save(1234,object(),data)
    review,response=fixture_values(fixture,draft)
    verifier=module.Verifier(lambda _:response,lambda _:review,lambda *_:False,uid(1),uid(9),[uid(5)])
    with pytest.raises(ValueError,match='independent direct human authorship'):
        decisions.DecisionRecorder(verifier.verify,OperatorStore(fixture),[REPO]).approve(dict(comment_id=uid(8),review_id=uid(10)))
    assert fixture.project(REPO,draft['project_id'])['governing_version'] is None


@pytest.mark.parametrize('change',['edited','app','author','issue','project','org','viewer','digest','comment','extra','bot','external','behalf','archived'])
def test_reject_wrong_or_ambiguous_source(setup_draft,change):
    writer,fixture,_,data=setup_draft;draft=writer.save(1234,object(),data)
    review,response=fixture_values(fixture,draft);response=copy.deepcopy(response);c=response['comment']
    if change=='edited':c['edited_at']='2026-11-12T12:00:01Z'
    elif change=='app':c['author_is_app']=True
    elif change=='author':c['author_id']=uid(11)
    elif change=='issue':c['issue_id']=uid(11)
    elif change=='project':c['project_id']=uid(11)
    elif change=='org':response['organization_id']=uid(11)
    elif change=='viewer':response['viewer_id']=uid(11)
    elif change=='digest':c['body']=c['body'].replace(draft['markdown_sha256'],'0'*64)
    elif change=='comment':c['id']=uid(11)
    elif change=='bot':c['bot_actor']=uid(11)
    elif change=='external':c['external_user']=uid(11)
    elif change=='behalf':c['on_behalf_of']=uid(5)
    elif change=='archived':c['archived_at']='2026-11-12T12:00:01Z'
    else:c['unexpected']=True
    verifier=module.Verifier(lambda _:response,lambda _:review,lambda *_:True,uid(1),uid(9),[uid(5)])
    with pytest.raises(ValueError):decisions.DecisionRecorder(verifier.verify,OperatorStore(fixture),[REPO]).approve(dict(comment_id=uid(8),review_id=uid(10)))
    assert fixture.project(REPO,draft['project_id'])['governing_version'] is None


def test_native_graphql_reader_composes_with_decision_verifier(setup_draft):
    writer,fixture,_,data=setup_draft;draft=writer.save(1234,object(),data)
    review,response=fixture_values(fixture,draft);c=response['comment']
    result={'data':{'viewer':{'id':uid(9),'organization':{'id':uid(1)}},'comment':{
        'id':c['id'],'body':c['body'],'createdAt':c['created_at'],'editedAt':None,'archivedAt':None,
        'botActor':None,'externalUser':None,'onBehalfOf':None,'user':{'id':uid(5),'app':False},
        'issue':{'id':uid(7),'team':{'id':uid(6)},'project':{'id':uid(3)}}}}}
    reader_path=path.with_name('onboarding_linear_comment_reader.py')
    reader_spec=importlib.util.spec_from_file_location('linear_comment_reader_test',reader_path)
    reader_module=importlib.util.module_from_spec(reader_spec);reader_spec.loader.exec_module(reader_module)
    calls=[]
    def graphql(request):
        calls.append(request)
        return result
    reader=reader_module.Reader(graphql,uid(9),uid(1))
    verifier=module.Verifier(reader,lambda _:review,lambda *_:True,uid(1),uid(9),[uid(5)])
    approved=decisions.DecisionRecorder(verifier.verify,OperatorStore(fixture),[REPO]).approve(dict(comment_id=uid(8),review_id=uid(10)))
    assert approved['version']==1 and calls[0]['variables']=={'id':uid(8)}
    result['data']['comment']['botActor']={'type':'oauthClient'}
    with pytest.raises(ValueError):verifier.verify(dict(comment_id=uid(8),review_id=uid(10)))
    del result['data']['comment']['botActor']
    with pytest.raises(ValueError):reader(uid(8))
