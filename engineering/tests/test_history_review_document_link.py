"""Exact passive document intake, real SQLite and lost-response/readback recovery."""
import copy
import os
import pytest
from jsonschema import ValidationError
from test_engineering_history_local import module,DOC
from test_history_managed_review import inputs

m=module('review_document_link');c=module('contract')


@pytest.fixture
def packet(inputs):
    package=module('managed_review').build(*inputs,DOC)
    return m.build({'work_request':inputs[2],'package':package})


@pytest.fixture
def linked(packet,tmp_path):
    root=tmp_path/'history';root.mkdir(mode=0o700);history=module('store').Store(root,create=True)
    history.submit(packet['work_request'],peer_uid=os.getuid())
    def call(message):
        if message['method']=='history':return history.history(offset=message['offset'],limit=message['limit'])
        if message['method']=='submit':return history.submit(message['request'],peer_uid=os.getuid())
        assert message['method']=='document'
        raw,manifest=history.document(message['document_id'],message['version'])
        return {'markdown':raw.decode(),'manifest':manifest,'authority_granted':False}
    state=tmp_path/'receiver';m.prepare(state,packet,m.inspect(packet)['packet_sha256'])
    return state,history,call


def test_packet_selects_only_private_passive_document_content(packet):
    assert packet['source_provenance']=='imported' and packet['authority_granted'] is False
    assert 'configuration' not in packet and 'approval' not in packet and 'narrative' not in packet
    assert m.inspect(packet)['history_records_written'] is False


@pytest.mark.parametrize('field',['markdown','manifest','binding','source_provenance','extra','work','source'])
def test_tampered_or_promoted_packet_refused(packet,field):
    packet=copy.deepcopy(packet)
    if field=='markdown':packet['markdown']+='changed'
    elif field=='manifest':packet['manifest']['renderer_sha256']='e'*64
    elif field=='binding':packet['binding']['document_request_sha256']='e'*64
    elif field=='source_provenance':packet['source_provenance']='observed'
    elif field=='extra':packet['approval']={'execution_authorized':True}
    elif field=='work':packet['work_request']['body']['allowed_paths']=['other.py']
    else:packet['document_request']['source']['kind']='human_reported'
    with pytest.raises((ValueError,ValidationError)):m.validate(packet)


def test_exact_review_digest_required_before_state_creation(packet,tmp_path):
    state=tmp_path/'receiver'
    with pytest.raises(ValueError,match='reviewed document'):m.prepare(state,packet,'f'*64)
    assert not state.exists()


def test_intake_exact_bytes_and_repeat_no_submit(linked,packet):
    state,history,call=linked
    result=m.deliver(state,call,writer_uid=os.getuid(),peer_uid=os.getuid())
    before=history.history();raw,manifest=history.document(DOC)
    assert raw.decode()==packet['markdown'] and manifest==packet['manifest']
    assert result['authority_granted'] is False and len(before['records'])==2
    def no_submit(message):
        assert message['method']!='submit';return call(message)
    assert m.deliver(state,no_submit,writer_uid=os.getuid(),peer_uid=os.getuid())==result
    assert history.history()==before


def test_lost_response_after_commit_replays_one_document(linked):
    state,history,call=linked
    def lost(message):
        answer=call(message)
        if message['method']=='submit':raise OSError('synthetic response lost after commit')
        return answer
    with pytest.raises(OSError):m.deliver(state,lost,writer_uid=os.getuid(),peer_uid=os.getuid())
    assert not (state/'complete.json').exists() and len(history.history()['records'])==2
    before=history.history();m.deliver(state,call,writer_uid=os.getuid(),peer_uid=os.getuid())
    assert history.history()==before


def test_readback_failure_retains_receipt_and_resumes_without_submit(linked):
    state,history,call=linked
    def wrong(message):
        answer=call(message)
        if message['method']=='document':answer['markdown']+='changed'
        return answer
    with pytest.raises(ValueError,match='readback'):m.deliver(state,wrong,writer_uid=os.getuid(),peer_uid=os.getuid())
    assert (state/'receipt.json').exists() and not (state/'complete.json').exists()
    def recover(message):
        assert message['method']!='submit';return call(message)
    m.deliver(state,recover,writer_uid=os.getuid(),peer_uid=os.getuid())
    assert len(history.history()['records'])==2


def test_missing_work_never_created(linked):
    state,_,_=linked
    def empty(message):
        assert message['method']=='history';return {'records':[],'has_more':False,'next_offset':0}
    with pytest.raises(ValueError,match='never create'):m.deliver(state,empty,writer_uid=os.getuid(),peer_uid=os.getuid())
    assert not (state/'receipt.json').exists()


def test_stale_engineering_head_refuses_before_document_write(linked,packet):
    state,history,call=linked;rev=copy.deepcopy(packet['work_request']);rev['operation']='work.revise'
    rev['client_event_key']='new-head';rev['expected_head']=c.digest(c.encoded(rev['body']));rev['body']['revision']=2
    history.submit(rev,peer_uid=os.getuid())
    with pytest.raises(ValueError,match='exact engineering'):m.deliver(state,call,writer_uid=os.getuid(),peer_uid=os.getuid())
    assert len(history.history()['records'])==2 and not (state/'receipt.json').exists()


@pytest.mark.parametrize('field',['manifest','peer','authority'])
def test_false_document_receipt_refused_without_completion(linked,field):
    state,_,call=linked
    def wrong(message):
        answer=call(message)
        if message['method']=='submit':
            if field=='manifest':answer['receipt']['document_manifest']['markdown_sha256']='f'*64
            elif field=='peer':answer['receipt']['peer_uid']=12345
            else:answer['receipt']['authority_granted']=True
        return answer
    with pytest.raises(ValueError):m.deliver(state,wrong,writer_uid=os.getuid(),peer_uid=os.getuid())
    assert not (state/'complete.json').exists() and not (state/'receipt.json').exists()


def test_same_receiver_concurrent_delivery_refused(linked):
    state,_,call=linked
    with module('managed_sync').locked(state):
        with pytest.raises(ValueError,match='another sync'):m.deliver(state,call,writer_uid=os.getuid(),peer_uid=os.getuid())
