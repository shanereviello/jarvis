"""Explicit receiver lifecycle, frozen inputs, no implicit work or control actions."""
import copy
import fcntl
import os
from pathlib import Path
import pytest
from jsonschema import ValidationError
from test_engineering_history_local import module
from test_history_managed_link import setup,exporter,j,fixtures

sync=module('managed_sync');c=module('contract')


@pytest.fixture
def linked(setup,tmp_path):
    journal,rows,packet,work,history=setup
    def call(message):
        if message['method']=='history':return history.history(offset=message['offset'],limit=message['limit'])
        assert message['method']=='submit'
        return history.submit(message['request'],peer_uid=os.getuid())
    root=tmp_path/'sync';sync.initialize(root,work,packet,'/run/synthetic-history/service.sock',os.getuid(),call)
    return root,journal,rows,packet,work,history,call


def handoff(path,packets):
    path.mkdir(mode=0o700);members=[]
    for index,packet in enumerate(packets):
        name=f'packet-{index:03d}.json';raw=c.encoded(packet);(path/name).write_bytes(raw);(path/name).chmod(0o600)
        members.append({'file':name,'sha256':c.digest(raw),'events':len(packet['facts'])})
    meta={'contract':'engineering-production-export-result.v1','work':packets[0]['work'],'journal_id':packets[0]['journal_id'],
          'packets':members,'next_after':packets[-1]['next_after'],'source_open_mode':'ro',
          'source_rows_written':False,'history_records_written':False,'api_calls':0}
    (path/'export-result.json').write_bytes(c.encoded(meta));(path/'export-result.json').chmod(0o600)
    return path


def test_inspect_does_not_deliver_and_wrong_review_digest_refuses(linked,tmp_path):
    root,_,_,packet,_,history,call=linked;source=handoff(tmp_path/'handoff',[packet]);before=history.history()
    review=sync.inspect(root,source);assert review['history_records_written'] is False
    with pytest.raises(ValueError,match='reviewed capture'):sync.apply(root,source,'f'*64,call)
    assert history.history()==before and list((root/'captures').iterdir())==[]


def test_apply_and_repeat_use_stable_receipts_without_reinserting(linked,tmp_path):
    root,_,_,packet,_,history,call=linked;source=handoff(tmp_path/'handoff',[packet]);sha=sync.inspect(root,source)['capture_sha256']
    done=sync.apply(root,source,sha,call);before=history.history()
    def read_only(message):
        assert message['method']=='history','completed delivery must not submit again'
        return call(message)
    assert sync.apply(root,source,sha,read_only)==done and history.history()==before
    assert sync.status(root)['unique_linked_source_events']==1
    assert sync.status(root)['source_freshness']=='not_polled'


def test_lost_response_resumes_without_original_handoff(linked,tmp_path):
    root,_,_,packet,_,history,call=linked;source=handoff(tmp_path/'handoff',[packet]);sha=sync.inspect(root,source)['capture_sha256']
    def lost(message):
        answer=call(message)
        if message['method']=='submit':raise OSError('synthetic lost response after commit')
        return answer
    with pytest.raises(OSError):sync.apply(root,source,sha,lost)
    before=history.history()
    for path in source.iterdir():path.unlink()
    source.rmdir()
    done=sync.resume(root,sha,call)
    assert done['next_after']==1 and history.history()==before


def test_new_full_capture_adds_only_new_event_and_rejects_regression(linked,tmp_path):
    root,journal,rows,packet,_,history,call=linked
    old=handoff(tmp_path/'old',[packet]);sync.apply(root,old,sync.inspect(root,old)['capture_sha256'],call)
    journal.append([fixtures.next_event(rows)])
    full=exporter.export(journal.root,packet['journal_id'],packet['work']['record_sha256'])
    new=handoff(tmp_path/'new',[full]);sync.apply(root,new,sync.inspect(root,new)['capture_sha256'],call)
    assert len(history.history()['records'])==3 and sync.status(root)['completed_source_cursor']==2
    with pytest.raises(ValueError,match='regresses'):sync.apply(root,old,sync.inspect(root,old)['capture_sha256'],call)


def test_all_pages_frozen_before_first_delivery(linked,tmp_path):
    root,journal,rows,packet,_,_,call=linked;journal.append([fixtures.next_event(rows)])
    first=exporter.export(journal.root,packet['journal_id'],packet['work']['record_sha256'],limit=1)
    second=exporter.export(journal.root,packet['journal_id'],packet['work']['record_sha256'],after=1)
    source=handoff(tmp_path/'two-pages',[first,second]);sha=sync.inspect(root,source)['capture_sha256']
    def offline(message):
        if message['method']=='submit':raise OSError('offline')
        return call(message)
    with pytest.raises(OSError):sync.apply(root,source,sha,offline)
    saved=sync.local('link_delivery').read(root/'captures'/('capture-'+sha)/'input.json')
    assert len(saved['packets'])==2 and sync.status(root)['completed_source_cursor']==0
    for path in source.iterdir():path.unlink()
    source.rmdir()
    assert sync.resume(root,sha,call)['next_after']==2


@pytest.mark.parametrize('change',['repository','scope','work','packet_bytes','packet_name','missing_page'])
def test_handoff_tamper_or_wrong_work_refused(linked,tmp_path,change):
    root,_,_,packet,_,_,_=linked;packet=copy.deepcopy(packet)
    if change=='repository':packet['work']['repository_id']='other'
    if change=='scope':packet['work']['requested_paths']=['other.py']
    if change=='work':packet['work']['work_item_id']='wrk_'+'f'*32
    source=handoff(tmp_path/'handoff',[packet])
    if change=='packet_bytes':(source/'packet-000.json').write_text('{}')
    if change=='packet_name':
        meta=sync.local('link_delivery').read(source/'export-result.json');meta['packets'][0]['file']='../secret'
        (source/'export-result.json').write_bytes(c.encoded(meta))
    if change=='missing_page':(source/'packet-000.json').unlink()
    with pytest.raises((ValueError,OSError,ValidationError)):
        sync.inspect(root,source)


def test_changed_engineering_head_refuses_before_submission(linked,tmp_path):
    root,_,_,packet,work,history,call=linked
    revised=copy.deepcopy(work);revised.update(operation='work.revise',client_event_key='new-revision',expected_head=c.digest(c.encoded(work['body'])))
    revised['body'].update(revision=2,objective='Changed intent');history.submit(revised,peer_uid=os.getuid())
    source=handoff(tmp_path/'handoff',[packet]);sha=sync.inspect(root,source)['capture_sha256']
    with pytest.raises(ValueError,match='exact engineering'):sync.apply(root,source,sha,call)
    assert not list((root/'captures').iterdir())


def test_unknown_work_is_never_created_implicitly(setup,tmp_path):
    _,_,packet,work,history=setup;empty=module('store');directory=tmp_path/'empty';directory.mkdir(mode=0o700);store=empty.Store(directory,create=True)
    def call(message):
        assert message['method']=='history';return store.history()
    with pytest.raises(ValueError,match='never create'):sync.initialize(tmp_path/'state',work,packet,'/run/test.sock',os.getuid(),call)
    assert store.history()['records']==[]


def test_same_state_concurrent_sync_is_refused(linked,tmp_path):
    root,_,_,packet,_,_,call=linked;source=handoff(tmp_path/'handoff',[packet]);sha=sync.inspect(root,source)['capture_sha256']
    with sync.locked(root):
        with pytest.raises(ValueError,match='another sync'):sync.apply(root,source,sha,call)


@pytest.mark.parametrize('change',['cursor','receipt'])
def test_status_refuses_corrupted_completion_or_missing_receipts(linked,tmp_path,change):
    root,_,_,packet,_,_,call=linked;source=handoff(tmp_path/'handoff',[packet]);sha=sync.inspect(root,source)['capture_sha256']
    sync.apply(root,source,sha,call);capture=root/'captures'/('capture-'+sha)
    if change=='cursor':
        path=capture/'complete.json';value=sync.local('link_delivery').read(path);value['next_after']=99;path.write_bytes(c.encoded(value))
    else:(capture/'page-000/receipt-000.json').unlink()
    with pytest.raises((ValueError,OSError)):sync.status(root)


def test_pending_page_must_match_frozen_review_before_delivery(linked,tmp_path):
    root,_,_,packet,_,_,call=linked;source=handoff(tmp_path/'handoff',[packet]);sha=sync.inspect(root,source)['capture_sha256']
    def offline(message):
        if message['method']=='submit':raise OSError('offline')
        return call(message)
    with pytest.raises(OSError):sync.apply(root,source,sha,offline)
    path=root/'captures'/('capture-'+sha)/'page-000/plan.json'
    value=sync.local('link_delivery').read(path);value['packet']['facts'][0]['outcome']='uncertain'
    value['plan']=sync.local('managed_link').plan(value['work_request'],value['packet'])
    path.write_bytes(c.encoded(value))
    with pytest.raises(ValueError,match='frozen input'):sync.resume(root,sha,call)
