"""Real disposable journals/history, allowlists, binding and delivery crash recovery."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import pytest
from jsonschema import ValidationError,Draft202012Validator
from test_engineering_history_local import module
import test_workflow_records as fixtures

link=module('managed_link');delivery=module('link_delivery');store_module=module('store');c=module('contract')
p=Path(__file__).resolve().parents[1]/'tools/rras_native/engineering_export.py'
s=importlib.util.spec_from_file_location('exporter',p);exporter=importlib.util.module_from_spec(s);s.loader.exec_module(exporter)
j=exporter.local('workflow_journal')


@pytest.fixture
def setup(tmp_path):
    root=tmp_path/'operational';root.mkdir(mode=0o700);journal=j.Journal(root,create=True)
    rows=fixtures.history('library-managed.json');journal.append(rows)
    sha=j.digest(j.encoded(rows[1]));before=journal.path.read_bytes()
    packet=exporter.export(root,'managed-production',sha)
    assert journal.path.read_bytes()==before
    source=packet['work']
    work={'contract':'engineering-history.v1','operation':'work.create','client_event_key':'explicit-work',
          'expected_head':None,'source':{'kind':'agent_reported','namespace':'fixture','id':None},'occurred_at':None,
          'body':{'work_item_id':source['work_item_id'],'repository_id':source['repository_id'],'revision':1,
                  'title':'Explicit linked work','objective':'Preserve intent and evidence','rationale':'Operator wants traceability',
                  'acceptance_criteria':[{'id':'AC1','description':'Source claims retain provenance'}],
                  'allowed_paths':source['requested_paths'],'baseline':source['baseline']}}
    directory=tmp_path/'engineering';directory.mkdir(mode=0o700);history=store_module.Store(directory,create=True);history.submit(work,peer_uid=1000)
    return journal,rows,packet,work,history


def test_export_schema_and_allowlist_preserve_hashes_without_private_text(setup):
    journal,rows,packet,work,history=setup
    Draft202012Validator.check_schema(json.loads(link.SCHEMA.read_text()))
    raw=c.encoded(packet)
    for secret in (rows[1]['objective'],rows[3]['summary']):assert secret.encode() not in raw
    assert b'authorization_reference' not in raw and b'actor' not in raw
    assert packet['facts'][0]['record_sha256']==j.digest(j.encoded(rows[3]))
    assert packet['work']['work_item_id']==work['body']['work_item_id']


def test_import_never_promotes_source_observation_to_authority(setup):
    _,_,packet,work,history=setup
    packet['facts'][0]['provenance']='observed'
    plan=link.plan(work,packet);request=plan['requests'][0]
    receipt=history.submit(request,peer_uid=1000)['receipt']
    assert request['source']['kind']=='imported' and receipt['provenance']=='imported'
    assert '"provenance":"observed"' in request['body']['summary']
    assert receipt['authority_granted'] is False and plan['release_status']=='not_inferred'


@pytest.mark.parametrize('field',['work_item_id','repository_id','baseline','allowed_paths'])
def test_mismatched_explicit_work_binding_refused(setup,field):
    _,_,packet,work,_=setup
    work=copy.deepcopy(work)
    work['body'][field]={'work_item_id':'wrk_'+'f'*32,'repository_id':'other','baseline':None,'allowed_paths':['other.py']}[field]
    with pytest.raises(ValueError,match='binding'):link.plan(work,packet)


@pytest.mark.parametrize('location',['packet','work','fact'])
def test_extra_private_or_authority_fields_refused(setup,location):
    _,_,packet,_,_=setup;packet=copy.deepcopy(packet)
    target={'packet':packet,'work':packet['work'],'fact':packet['facts'][0]}[location];target['execution_authorized']=True
    with pytest.raises(ValidationError):link.validate(packet)


@pytest.mark.parametrize('url',['https://token@example.com/a/b/pull/1','https://example.com/a/b/pull/1?token=x','file:///etc/shadow','https://example.com/a/b/pull/1#x','ssh://example.com/a/b'])
def test_reference_sanitization_refuses_credentials_or_nonpublic_forms(url):
    assert not link.public_reference({'namespace':'pull_request','id':url})


def test_pagination_is_explicit_and_overlap_deduplicates(setup):
    journal,rows,packet,work,history=setup
    journal.append([fixtures.next_event(rows)])
    all_events=exporter.export(journal.root,packet['journal_id'],packet['work']['record_sha256'])
    first=exporter.export(journal.root,packet['journal_id'],packet['work']['record_sha256'],limit=1)
    assert first['has_more'] and first['next_after']==1
    a=link.plan(work,first)['requests'][0];b=link.plan(work,all_events)['requests'][0]
    assert a==b
    one=history.submit(a,peer_uid=1000);two=history.submit(b,peer_uid=1000)
    assert one['receipt']==two['receipt'] and not two['inserted']


def test_lost_response_does_not_advance_cursor_or_duplicate_record(setup,tmp_path):
    _,_,packet,work,history=setup;state=tmp_path/'delivery'
    delivery.prepare(state,work,packet)
    def lost(request):
        history.submit(request,peer_uid=1000)
        raise OSError('synthetic response lost after commit')
    with pytest.raises(OSError):delivery.deliver(state,lost,writer_uid=os.getuid(),peer_uid=1000)
    assert not (state/'complete.json').exists()
    before=history.history()
    result=delivery.deliver(state,lambda request:history.submit(request,peer_uid=1000),writer_uid=os.getuid(),peer_uid=1000)
    assert result['next_after']==packet['next_after'] and history.history()==before
    assert delivery.deliver(state,lambda _:pytest.fail('saved receipt must avoid delivery'),writer_uid=os.getuid(),peer_uid=1000)==result


def test_changed_source_event_under_same_identity_conflicts(setup):
    _,_,packet,work,history=setup
    original=link.plan(work,packet)['requests'][0];history.submit(original,peer_uid=1000)
    changed=copy.deepcopy(packet);changed['facts'][0]['outcome']='uncertain';changed['facts'][0]['record_sha256']='f'*64
    revised=link.plan(work,changed)['requests'][0]
    assert revised['client_event_key']==original['client_event_key']
    with pytest.raises(ValueError,match='idempotency'):history.submit(revised,peer_uid=1000)


def test_changed_engineering_head_refuses_without_rewriting_narrative(setup):
    _,_,packet,work,history=setup
    revised=copy.deepcopy(work);revised.update(operation='work.revise',client_event_key='scope-change',expected_head=c.digest(c.encoded(work['body'])))
    revised['body']['revision']=2;revised['body']['objective']='Changed scope'
    history.submit(revised,peer_uid=1000)
    with pytest.raises(ValueError,match='revision'):history.submit(link.plan(work,packet)['requests'][0],peer_uid=1000)


def test_export_selects_exact_old_or_new_operational_revision(setup):
    journal,rows,packet,_,_=setup
    revised=copy.deepcopy(rows[1]);revised.update(revision=2,supersedes_sha256=packet['work']['record_sha256'],objective='New private objective')
    event=fixtures.next_event(rows);event.update(work_item_sha256=j.digest(j.encoded(revised)),attempt_id=None)
    journal.append([revised,event])
    old=exporter.export(journal.root,packet['journal_id'],packet['work']['record_sha256'])
    new=exporter.export(journal.root,packet['journal_id'],j.digest(j.encoded(revised)))
    assert [f['sequence'] for f in old['facts']]==[1]
    assert [f['sequence'] for f in new['facts']]==[2]
    assert old['work']['revision']==1 and new['work']['revision']==2
    with pytest.raises(ValueError,match='exact operational'):exporter.export(journal.root,packet['journal_id'],'f'*64)


@pytest.mark.parametrize('change',['cursor','duplicate','order','private_field','reference'])
def test_tampered_packet_cursors_or_members_refused(setup,change):
    _,_,packet,_,_=setup;packet=copy.deepcopy(packet)
    if change=='cursor':packet['next_after']+=1
    if change=='duplicate':packet['facts'].append(copy.deepcopy(packet['facts'][0]))
    if change=='order':packet['after']=packet['next_after']
    if change=='private_field':packet['facts'][0]['summary']='private content'
    if change=='reference':packet['facts'][0]['public_references']=[{'namespace':'pull_request','id':'https://token@example.com/a/b/pull/1'}]
    with pytest.raises((ValueError,ValidationError)):link.validate(packet)


def test_poisoned_receipt_does_not_advance_cursor(setup,tmp_path):
    _,_,packet,work,history=setup;state=tmp_path/'delivery';delivery.prepare(state,work,packet)
    def poisoned(request):
        answer=history.submit(request,peer_uid=1000);answer['receipt']['provenance']='observed';return answer
    with pytest.raises(ValueError,match='association'):delivery.deliver(state,poisoned,writer_uid=os.getuid(),peer_uid=1000)
    assert not (state/'complete.json').exists() and not (state/'receipt-000.json').exists()


def test_modified_prepared_plan_refused_before_delivery(setup,tmp_path):
    _,_,packet,work,_=setup;state=tmp_path/'delivery';delivery.prepare(state,work,packet)
    saved=json.loads((state/'plan.json').read_bytes());saved['plan']['next_after']+=1
    (state/'plan.json').write_bytes(c.encoded(saved))
    with pytest.raises(ValueError,match='plan differs'):
        delivery.deliver(state,lambda _:pytest.fail('modified plan cannot deliver'),writer_uid=os.getuid(),peer_uid=1000)


def test_no_new_intake_operation_or_store_schema_needed(setup):
    _,_,packet,work,history=setup
    for request in link.plan(work,packet)['requests']:history.submit(request,peer_uid=1000)
    assert history.history()['records'][-1]['submission']['operation']=='checkpoint.append'
    with history.connection() as db:assert db.execute('PRAGMA user_version').fetchone()==(1,)


def test_next_page_requires_completed_matching_prior_cursor(setup,tmp_path):
    journal,rows,packet,work,history=setup;journal.append([fixtures.next_event(rows)])
    first=exporter.export(journal.root,packet['journal_id'],packet['work']['record_sha256'],limit=1)
    second=exporter.export(journal.root,packet['journal_id'],packet['work']['record_sha256'],after=first['next_after'])
    one=tmp_path/'one';two=tmp_path/'two';delivery.prepare(one,work,first)
    with pytest.raises(ValueError,match='cursor zero'):delivery.prepare(two,work,second)
    with pytest.raises(FileNotFoundError):delivery.prepare(two,work,second,previous=one)
    delivery.deliver(one,lambda request:history.submit(request,peer_uid=1000),writer_uid=os.getuid(),peer_uid=1000)
    delivery.prepare(two,work,second,previous=one)
    result=delivery.deliver(two,lambda request:history.submit(request,peer_uid=1000),writer_uid=os.getuid(),peer_uid=1000)
    assert result['next_after']==2


def test_source_cli_exports_and_prepares_without_live_service(setup,tmp_path):
    import subprocess,sys
    journal,_,packet,work,_=setup
    outputdir=tmp_path/'private-input';outputdir.mkdir(mode=0o700)
    packet_path=outputdir/'packet.json';work_path=outputdir/'work.json'
    work_path.write_bytes(c.encoded(work));work_path.chmod(0o600)
    result=subprocess.run([sys.executable,str(p),'--store',str(journal.root),'--journal-id',packet['journal_id'],
                           '--work-sha256',packet['work']['record_sha256'],'--output',str(packet_path)],capture_output=True,text=True)
    assert result.returncode==0 and json.loads(result.stdout)['source_mutations'] is False
    assert packet_path.stat().st_mode&0o777==0o600
    cli=p.parent.parent/'rras_history/managed_link_cli.py'
    state=tmp_path/'prepared'
    result=subprocess.run([sys.executable,str(cli),'prepare','--state',str(state),'--packet',str(packet_path),
                           '--work-request',str(work_path)],capture_output=True,text=True)
    assert result.returncode==0 and json.loads(result.stdout)['delivery_started'] is False
    assert not (state/'complete.json').exists()


def test_sensitive_raw_artifact_bytes_are_not_read_or_exported(setup):
    journal,rows,packet,_,_=setup
    event=fixtures.next_event(rows);raw=b'synthetic private provider log must never cross bridge'
    sha=j.digest(raw);event['artifacts']=[{'artifact_id':'art_'+'8'*32,'sha256':sha,'media_type':'text/plain','visibility':'operator_only','purpose':'validation'}]
    journal.append([event],{sha:raw})
    result=exporter.export(journal.root,packet['journal_id'],packet['work']['record_sha256'])
    assert raw not in c.encoded(result)
    assert result['facts'][-1]['artifacts']==[{'artifact_id':'art_'+'8'*32,'sha256':sha,'purpose':'validation'}]
