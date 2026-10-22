"""Real disposable SQLite, deterministic documents, no service/root/provider."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import pytest
from jsonschema import ValidationError

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'tools/rras_history'

def module(name):
    s=importlib.util.spec_from_file_location('test_history_'+name,TOOLS/(name+'.py'))
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

c=module('contract');m=module('store')
WORK='wrk_'+'1'*32
DOC='doc_'+'2'*32

def request(operation='work.create',key='initial',head=None,body=None):
    if body is None:
        body=dict(work_item_id=WORK,revision=1,repository_id='example',title='Bounded fixture',
                  objective='Explain a change',rationale='Operator wants traceability',
                  acceptance_criteria=[{'id':'AC1','description':'Intent and evidence remain distinct'}],
                  allowed_paths=['docs/example.md'],baseline=None)
    return dict(contract='engineering-history.v1',operation=operation,client_event_key=key,
                expected_head=head,source={'kind':'agent_reported','namespace':'fixture','id':None},
                occurred_at=None,body=body)

@pytest.fixture
def store(tmp_path):
    root=tmp_path/'private';root.mkdir(mode=0o700)
    return m.Store(root,create=True)

def create(store):
    return store.submit(request())['receipt']['work_revision_sha256']

def note(head,key='note',work=WORK):
    return request('checkpoint.append',key,head,dict(work_item_id=work,work_revision_sha256=head,
        checkpoint_type='handoff',summary='Work remains unfinished',decisions=[],next_action='Review scope',references=[]))

def document(head,kind='review',key='render'):
    template=(ROOT/'docs/engineering-history-phase1/templates'/f'{kind}.md').read_text()
    injected={'work_item_id','work_revision','document_id','document_version','repository_id','created_at_or_unknown'}
    fields={name:'unknown' for name in set(re.findall(r'\{\{([a-z][a-z0-9_]*)\}\}',template))-injected}
    fields['title']='A curated engineering draft'
    return request('document.render',key,head,dict(work_item_id=WORK,work_revision_sha256=head,
        document_id=DOC,document_version=1,document_type=kind,supersedes_document_sha256=None,fields=fields,references=[]))


def test_atomic_receipts_reopen_and_duplicate_without_new_events(store):
    submitted=request();first=store.submit(submitted)
    reopened=m.Store(store.root)
    duplicate=reopened.submit(submitted)
    assert first['inserted'] and not duplicate['inserted'] and first['receipt']==duplicate['receipt']
    assert len(reopened.history()['records'])==1 and len(reopened.pending()['pending'])==1
    assert first['receipt']['transport']=='local_caller_store'
    assert first['receipt']['authority_granted'] is False
    assert first['receipt']['visibility']=='operator_private'
    assert first['receipt']['writer_uid']==os.getuid()
    assert store.path.stat().st_mode&0o777==0o600
    assert reopened.history()['records'][0]['submission']['occurred_at'] is None


def test_conflicting_idempotency_key_refuses_without_overwrite(store):
    first=store.submit(request());changed=request();changed['body']['objective']='Different'
    with pytest.raises(ValueError,match='idempotency'):store.submit(changed)
    assert store.history()['records'][0]['receipt']==first['receipt']


def test_failed_outbox_write_rolls_back_record_and_receipt(store):
    with patch.object(store,'queue',side_effect=OSError('synthetic storage failure')):
        with pytest.raises(OSError):store.submit(request())
    reopened=m.Store(store.root)
    assert reopened.history()['records']==[] and reopened.pending()['pending']==[]
    assert reopened.submit(request())['inserted']


def test_race_two_scope_updates_has_one_winner(store):
    head=create(store)
    def submit(number):
        r=request('work.revise','revision-'+str(number),head);r['body']['revision']=2;r['body']['objective']=f'Choice {number}'
        try:return m.Store(store.root).submit(r)['inserted']
        except ValueError:return False
    with ThreadPoolExecutor(max_workers=2) as executor:results=list(executor.map(submit,[1,2]))
    assert sorted(results)==[False,True]
    assert len(store.history()['records'])==2


def test_revision_rejects_repository_change_and_stale_notes(store):
    head=create(store);r=request('work.revise','rev',head);r['body']['revision']=2
    wrong=copy.deepcopy(r);wrong['body']['repository_id']='another'
    with pytest.raises(ValueError):store.submit(wrong)
    new=store.submit(r)['receipt']['work_revision_sha256'];assert new!=head
    with pytest.raises(ValueError,match='current work'):store.submit(note(head))
    assert store.submit(note(new))['inserted']


def test_same_key_concurrent_retries_return_same_receipt(store):
    def submit(_):return m.Store(store.root).submit(request())
    with ThreadPoolExecutor(max_workers=2) as executor:results=list(executor.map(submit,[1,2]))
    assert sorted(x['inserted'] for x in results)==[False,True]
    assert results[0]['receipt']==results[1]['receipt']


@pytest.mark.parametrize('kind',['review','checkpoint','completion'])
def test_document_exact_bytes_manifest_and_old_version_survive_new_renderer(store,kind):
    head=create(store);r=document(head,kind);first=store.submit(r)
    raw,manifest=store.document(DOC)
    assert c.digest(raw)==manifest['markdown_sha256']
    assert b'status: draft_not_approval' in raw and b'visibility: operator_private' in raw
    assert first['receipt']['document_manifest']==manifest
    rendered=module('documents').render(r,request()['body'])
    assert rendered==(raw,manifest)
    original=m.local
    with patch.object(m,'local',side_effect=lambda name: (_ for _ in ()).throw(AssertionError('must not re-render')) if name=='documents' else original(name)):
        assert store.document(DOC)==(raw,manifest)
    r2=copy.deepcopy(r);r2['client_event_key']='version2';r2['body']['document_version']=2
    r2['body']['supersedes_document_sha256']=manifest['markdown_sha256'];r2['body']['fields']['title']='Updated account'
    store.submit(r2)
    assert m.Store(store.root).document(DOC,1)==(raw,manifest)
    assert store.document(DOC)[0]!=raw
    with pytest.raises(ValueError):store.submit({**r2,'client_event_key':'invalid-repeat'})


@pytest.mark.parametrize('change',['extra_field','missing_field','metadata_override','unknown_type','bad_parent','wrong_work'])
def test_document_refusals_create_no_partial_record(store,change):
    head=create(store);r=document(head)
    if change=='extra_field':r['body']['fields']['arbitrary']='injected'
    elif change=='missing_field':del r['body']['fields']['title']
    elif change=='metadata_override':r['body']['fields']['work_item_id']='spoofed'
    elif change=='unknown_type':r['body']['document_type']='html'
    elif change=='bad_parent':r['body']['supersedes_document_sha256']='f'*64
    elif change=='wrong_work':r['body']['work_item_id']='wrk_'+'3'*32
    with pytest.raises((ValueError,ValidationError)):store.submit(r)
    assert len(store.history()['records'])==1


@pytest.mark.parametrize('change',['observed','actor','authority','wrong_contract','extra_body','id_newline','bad_time','duplicate_criterion','traversal','nul','bool_revision','oversize'])
def test_contract_rejects_spoofing_malformed_or_out_of_scope_values(change):
    r=request()
    if change=='observed':r['source']['kind']='observed'
    elif change=='actor':r['source']['actor']='root'
    elif change=='authority':r['execution_authorized']=True
    elif change=='wrong_contract':r['contract']='workflow-v1'
    elif change=='extra_body':r['body']['unrecognized']=True
    elif change=='id_newline':r['body']['work_item_id']+='\n'
    elif change=='bad_time':r['occurred_at']='2026-02-30T00:00:00Z'
    elif change=='duplicate_criterion':r['body']['acceptance_criteria']*=2
    elif change=='traversal':r['body']['allowed_paths']=['../secret']
    elif change=='nul':r['body']['objective']='x\0y'
    elif change=='bool_revision':r['body']['revision']=True
    elif change=='oversize':r['body']['objective']='x'*(c.MAX_REQUEST+1)
    with pytest.raises((ValueError,ValidationError)):c.validate(r)


def test_duplicate_json_keys_nan_and_bound_refused():
    for raw in (b'{"a":1,"a":2}',b'{"n":NaN}',b' '*(c.MAX_REQUEST+1)):
        with pytest.raises(ValueError):c.decode(raw)


def test_interactive_session_and_failure_are_reports_not_authority(store):
    head=create(store)
    attached=request('session.attach','session',head,dict(work_item_id=WORK,work_revision_sha256=head,client_namespace='codex',session_id=None))
    store.submit(attached);store.submit(note(head))
    r=request('outcome.record','failed',head,dict(work_item_id=WORK,work_revision_sha256=head,outcome='failed',summary='Interrupted; no verification',references=[]))
    result=store.submit(r);assert not result['receipt']['authority_granted']
    assert [row['submission']['operation'] for row in store.history()['records']]==['work.create','session.attach','checkpoint.append','outcome.record']
    assert store.history(WORK,limit=2)['has_more'] and len(store.history(WORK,offset=2)['records'])==2


@pytest.mark.parametrize('offset,limit',[(-1,1),(0,0),(0,101),(True,10),(0,True)])
def test_pagination_bounds(store,offset,limit):
    with pytest.raises(ValueError):store.history(offset=offset,limit=limit)
    with pytest.raises(ValueError):store.pending(offset=offset,limit=limit)


def test_database_update_delete_and_outbox_removal_refused(store):
    create(store)
    with sqlite3.connect(store.path) as db:
        for sql in ('UPDATE submissions SET client_key="changed"','DELETE FROM submissions','DELETE FROM outbox'):
            with pytest.raises(sqlite3.IntegrityError):db.execute(sql)


def test_store_init_cannot_overwrite_or_adopt_wrong_modes_or_symlinks(store,tmp_path):
    with pytest.raises(FileExistsError):m.Store(store.root,create=True)
    store.path.chmod(0o644)
    with pytest.raises(ValueError):m.Store(store.root)
    store.path.chmod(0o600)
    link=tmp_path/'link';link.symlink_to(store.root,target_is_directory=True)
    with pytest.raises(ValueError):m.Store(link)
    store.root.chmod(0o755)
    with pytest.raises(ValueError):m.Store(store.root)


def test_unprivileged_only_before_any_database_access(tmp_path):
    with patch.object(m.os,'getuid',return_value=0),patch.object(m.os,'geteuid',return_value=0):
        with pytest.raises(ValueError,match='unprivileged'):m.Store(tmp_path,create=True)


def test_subprocess_cli_init_submit_reopen_and_document(tmp_path):
    root=tmp_path/'cli';root.mkdir(mode=0o700)
    def cli(*args):
        return subprocess.run([sys.executable,str(TOOLS/'cli.py'),*args,'--store',str(root)],capture_output=True,check=True)
    assert json.loads(cli('init').stdout)['initialized']
    input_path=tmp_path/'request.json';input_path.write_bytes(c.encoded(request()))
    result=json.loads(cli('submit','--request',str(input_path)).stdout)
    head=result['receipt']['work_revision_sha256'];input_path.write_bytes(c.encoded(document(head)))
    cli('submit','--request',str(input_path))
    assert b'# Engineering review' in cli('document','--document-id',DOC).stdout
    assert len(json.loads(cli('outbox').stdout)['pending'])==2
    assert len(json.loads(cli('history').stdout)['records'])==2


def test_lost_response_after_commit_keeps_original_receipt_and_outbox(store):
    with patch.object(store,'sync',side_effect=OSError('synthetic lost response')):
        with pytest.raises(OSError):store.submit(request())
    result=m.Store(store.root).submit(request())
    assert not result['inserted'] and result['receipt']['sequence']==1
    assert len(store.pending()['pending'])==1


def test_fixed_encoding_vector_and_strict_utf8():
    assert c.encoded({'z':'é','a':1})==b'{"a":1,"z":"\xc3\xa9"}\n'
    with pytest.raises(ValueError):c.decode('{"key":1}'.encode('utf-16'))
    with pytest.raises(ValueError):c.decode(b'['*2000+b']'*2000)


@pytest.mark.parametrize('stamp',['2026-10-22T12:00:00+00:00','2026-10-22T12:00:00Z\n','2026-10-22T24:00:00Z'])
def test_utc_format_and_calendar_without_optional_checker_dependencies(stamp):
    r=request();r['occurred_at']=stamp
    with pytest.raises((ValueError,ValidationError)):c.validate(r)


def test_capacity_refusal_preserves_prior_records_and_duplicate_receipts(store):
    first=store.submit(request())
    with patch.object(m,'MAX_RECORDS',1):
        assert not store.submit(request())['inserted']
        with pytest.raises(ValueError,match='capacity'):store.submit(note(first['receipt']['work_revision_sha256']))
    assert len(store.history()['records'])==1


def test_special_database_and_sidecar_refused_without_following_target(store,tmp_path):
    link=tmp_path/'database-link';store.path.rename(link);store.path.symlink_to(link)
    with pytest.raises(ValueError):m.Store(store.root)
    store.path.unlink();link.rename(store.path)
    sidecar=Path(str(store.path)+'-journal');sidecar.symlink_to(link)
    with pytest.raises(ValueError):m.Store(store.root)


def test_document_size_limit_does_not_commit_partial_content(store):
    head=create(store);r=document(head)
    for key in r['body']['fields']:r['body']['fields'][key]='x'*2000
    r['body']['fields']['title']='A bounded title'
    docs=m.local('documents');original=m.local
    with patch.object(docs,'MAX_DOCUMENT',128),patch.object(m,'local',side_effect=lambda name:docs if name=='documents' else original(name)):
        with pytest.raises(ValueError,match='document exceeds'):store.submit(r)
    assert len(store.history()['records'])==1 and len(store.pending()['pending'])==1


@pytest.mark.parametrize('kind',['symlink','fifo','directory'])
def test_cli_refuses_nonregular_request_without_blocking_or_recording(store,tmp_path,kind):
    target=tmp_path/'request'
    if kind=='symlink':target.symlink_to(tmp_path/'unavailable')
    elif kind=='fifo':os.mkfifo(target)
    else:target.mkdir()
    result=subprocess.run([sys.executable,str(TOOLS/'cli.py'),'submit','--store',str(store.root),'--request',str(target)],capture_output=True,timeout=5)
    assert result.returncode==1 and b'operation refused' in result.stderr
    assert store.history()['records']==[]


def test_repository_examples_execute_against_disposable_store(store):
    for name in ('work','checkpoint','document'):
        result=store.submit(json.loads((ROOT/f'contracts/examples/history-local-{name}.json').read_text()))
        assert result['inserted'] and not result['receipt']['authority_granted']
    raw,manifest=store.document('doc_'+'b'*32)
    assert b'Synthetic review; no approval' in raw
    assert manifest['visibility']=='operator_private'
    assert len(store.pending()['pending'])==3


def test_direct_renderer_refuses_wrong_revision_and_counterfeit_work_identity(store):
    head=create(store);r=document(head);wrong=request()['body'];wrong['objective']='Changed source intent'
    with pytest.raises(ValueError,match='exact work'):module('documents').render(r,wrong)
    wrong=copy.deepcopy(r);wrong['expected_head']='f'*64
    with pytest.raises(ValueError,match='exact work'):module('documents').render(wrong,request()['body'])


def test_open_store_rechecks_private_root_on_every_operation(store):
    create(store);store.root.chmod(0o755)
    with pytest.raises(ValueError,match='0700'):store.history()
    with pytest.raises(ValueError,match='0700'):store.submit(note('f'*64))
