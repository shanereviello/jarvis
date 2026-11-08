"""Reusable project/field publication, exact citations and withdrawal safety."""
import copy
import uuid
import pytest
from test_engineering_history_local import module,store
from test_history_projects import projects,P1,REPO
from test_history_reporting import reporting,request
from test_history_evidence import evidence,manifest

m=module('curated_reporting');catalog=module('curated_publication');c=module('contract')


@pytest.fixture
def profile():
    return dict(contract='engineering-reporting-publication-profile.v1',profile_id='prf_'+'1'*32,version=1,
        projects=[dict(project_id=P1,repository_id='jarvis')],
        fields={'checkpoint.report':['observations','changes','validation','next_step']},
        authorization_reference='Synthetic approved profile; no real publication')


def rows(reporting):
    with reporting.store.connection() as db:return [dict(submission=r,receipt=receipt) for r,receipt in reporting.events(db)]


def sha(profile):return c.digest(c.encoded(profile))


def checkpoint(reporting,projects):
    value=request(projects,'checkpoint.report')
    value['body']['report_id']='rpt_'+uuid.uuid4().hex
    value['body']['observations']=['Useful engineering finding\nAuthorization: Bearer SHOULD-NOT-PUBLISH']
    value['body']['alternatives_and_reasons']=['UNSELECTED-FIELD-MARKER']
    value['body']['next_step']='Verify independent acceptance'
    reporting.submit(value);return value


def test_selected_fields_redaction_exact_source_and_transcripts_excluded(profile,reporting,projects,evidence):
    value=checkpoint(reporting,projects);reporting.submit(manifest(projects,b'',context=False))
    preview=m.build(rows(reporting),profile,sha(profile));encoded=c.encoded(preview)
    assert len(preview['entries'])==1
    assert all(token not in encoded for token in (b'SHOULD-NOT-PUBLISH',b'UNSELECTED-FIELD-MARKER',b'content_sha256'))
    entry=preview['entries'][0]
    assert entry['context']==value['context'] and entry['source_request_sha256']==c.digest(c.encoded(value))
    assert entry['human_authenticated'] is False and entry['source_authenticated'] is False
    assert not preview['publication_authorized'] and 'Useful engineering finding' in c.encoded(entry).decode()


def test_profile_hash_and_arbitrary_fields_refused_before_publication(profile,reporting,projects):
    checkpoint(reporting,projects)
    with pytest.raises(ValueError):m.build(rows(reporting),profile,'0'*64)
    changed=copy.deepcopy(profile);changed['fields']['artifact.record']=['chunks']
    with pytest.raises(ValueError):m.build(rows(reporting),changed,sha(changed))
    changed=copy.deepcopy(profile);changed['fields']['linear.observe']=['snapshot_text']
    with pytest.raises(ValueError):m.build(rows(reporting),changed,sha(changed))


def test_reusable_profile_no_per_checkpoint_selection_and_withdrawal_not_resurrected(profile,reporting,projects,tmp_path):
    checkpoint(reporting,projects);root=tmp_path/'catalog';catalog.initialize(root,['jarvis'])
    with pytest.raises(ValueError,match='profile approval'):m.publish_profile(root,rows(reporting),profile,sha(profile),None)
    first=m.publish_profile(root,rows(reporting),profile,sha(profile),None,approve_profile=True)
    generation=first['generation_sha256'];page=catalog.search(root,'jarvis','finding')
    entry=page['entries'][0];assert page['generation_sha256']==generation
    assert m.publish_profile(root,rows(reporting),profile,sha(profile),generation,approve_profile=True)['replayed']
    withdrawn=catalog.withdraw(root,[entry['entry_id']],generation,'operator-withdrawal',approve_withdrawal=True)
    generation=withdrawn['generation_sha256']
    assert catalog.search(root,'jarvis','')['entries']==[]
    checkpoint(reporting,projects)
    published=m.publish_profile(root,rows(reporting),profile,sha(profile),generation,approve_profile=True)
    current=catalog.search(root,'jarvis','')
    assert published['generation_sha256']!=generation
    assert len(current['entries'])==1 and current['entries'][0]['entry_id']!=entry['entry_id']
    with pytest.raises(ValueError,match='stale catalog'):catalog.search(root,'jarvis','',generation_sha256=generation)
    access=module('curated_read_access').Access(root,dict(contract='engineering-curated-read-access.v1',
        principals=[dict(uid=2001,repositories=['jarvis']),dict(uid=2002,repositories=[])]))
    message=dict(method='read',repository_id='jarvis',entry_id=current['entries'][0]['entry_id'],generation_sha256=current['generation_sha256'])
    assert access.dispatch(2001,message)['entry']['context']['project_id']==P1
    with pytest.raises(ValueError):access.dispatch(2002,message)
    with pytest.raises(ValueError):access.dispatch(2001,dict(message,method='private_history'))


def test_out_of_profile_projects_and_forged_entry_fields_are_rejected(profile,reporting,projects):
    checkpoint(reporting,projects);preview=m.build(rows(reporting),profile,sha(profile))
    changed=copy.deepcopy(preview);entry=changed['entries'][0];entry['details']['snapshot_text']='FULL-TRANSCRIPT'
    entry['entry_id']='cur_'+c.digest(c.encoded({k:v for k,v in entry.items() if k!='entry_id'}))
    with pytest.raises(Exception):m.validate_preview(changed)
    changed=copy.deepcopy(preview);entry=changed['entries'][0];entry['context']['project_id']='prj_'+'9'*32
    entry['entry_id']='cur_'+c.digest(c.encoded({k:v for k,v in entry.items() if k!='entry_id'}))
    with pytest.raises(ValueError):m.validate_preview(changed)


def test_installed_profile_executes_through_bounded_writer_without_reapproval(profile,reporting,projects,tmp_path):
    checkpoint(reporting,projects);root=tmp_path/'catalog';catalog.initialize(root,['jarvis'])
    writer=module('curated_publication_entry')
    def apply(packet):
        raw=c.encoded(packet);return writer.apply(root,raw,c.digest(raw))
    execution=dict(contract='engineering-curated-profile-execution.v1',operation='publish_profile',
        profile_sha256=sha(profile),expected_head=None,rows=rows(reporting))
    with pytest.raises((ValueError,OSError)):apply(execution)
    install=dict(contract='engineering-curated-publication-request.v1',operation='install_profile',
        client_key='reviewed-profile',expected_head=None,approved=True,profile=profile,reviewed_profile_sha256=sha(profile))
    approved=apply(install);assert approved['human_authenticated'] is False
    assert apply(install)==approved
    first=apply(execution);assert first['publication_recorded']
    execution['expected_head']=first['generation_sha256'];assert apply(execution)['replayed']
    # Unselected fields or a changed profile cannot be supplied in execution.
    with pytest.raises(ValueError):apply(dict(execution,profile=profile))
    with pytest.raises((ValueError,OSError)):apply(dict(execution,profile_sha256='0'*64))
