"""Operator commands preserve explicit approval and durable document recovery."""
import copy
import os
import pytest
from test_engineering_history_local import module,DOC
from test_history_managed_review import inputs

cli=module('review_document_cli');link=module('review_document_link');c=module('contract');d=module('link_delivery')


@pytest.fixture
def prepared(inputs,tmp_path):
    packet=link.build({'work_request':inputs[2],'package':module('managed_review').build(*inputs,DOC)})
    path=tmp_path/'packet.json';d.write(path,packet)
    sha=link.inspect(packet)['packet_sha256'];state=tmp_path/'client'
    cli.prepare(state,path,sha,str(tmp_path/'service.sock'),os.getuid())
    history_path=tmp_path/'history';history_path.mkdir(mode=0o700);store=module('store').Store(history_path,create=True)
    store.submit(packet['work_request'],peer_uid=os.getuid())
    def call(message):
        if message['method']=='history':return store.history(offset=message['offset'],limit=message['limit'])
        if message['method']=='submit':return store.submit(message['request'],peer_uid=os.getuid())
        raw,manifest=store.document(message['document_id'],message['version'])
        return dict(markdown=raw.decode(),manifest=manifest,authority_granted=False)
    return state,packet,sha,store,call,path


def test_preparation_and_status_are_local_only(prepared):
    state,packet,sha,store,_,_=prepared
    status=cli.status(state)
    assert status['packet_sha256']==sha and not status['receipt_saved'] and not status['completion_saved']
    assert len(store.history()['records'])==1


@pytest.mark.parametrize('approved,sha',[(False,None),(True,'f'*64)])
def test_approval_and_exact_hash_before_any_call(prepared,approved,sha):
    state,_,correct,_,_,_=prepared
    def denied(_):raise AssertionError('service should not be contacted')
    with pytest.raises(ValueError,match='explicit exact'):cli.apply(state,sha or correct,approved,denied)


def test_apply_then_resume_does_not_resubmit(prepared):
    state,packet,sha,store,call,_=prepared
    result=cli.apply(state,sha,True,call)
    assert result['authority_granted'] is False and cli.status(state)['completion_saved']
    def no_submit(message):
        assert message['method']!='submit';return call(message)
    assert cli.apply(state,sha,True,no_submit)==result
    assert len(store.history()['records'])==2


def test_lost_response_resumes_one_document(prepared):
    state,_,sha,store,call,_=prepared
    def lost(message):
        result=call(message)
        if message['method']=='submit':raise OSError('response lost after commit')
        return result
    with pytest.raises(OSError):cli.apply(state,sha,True,lost)
    assert not cli.status(state)['receipt_saved'] and len(store.history()['records'])==2
    cli.apply(state,sha,True,call)
    assert cli.status(state)['completion_saved'] and len(store.history()['records'])==2


def test_readback_failure_resumes_without_submission(prepared):
    state,_,sha,store,call,_=prepared
    def lost(message):
        if message['method']=='document':raise OSError('readback interrupted')
        return call(message)
    with pytest.raises(OSError):cli.apply(state,sha,True,lost)
    assert cli.status(state)['receipt_saved'] and not cli.status(state)['completion_saved']
    def no_submit(message):
        assert message['method']!='submit';return call(message)
    cli.apply(state,sha,True,no_submit)
    assert len(store.history()['records'])==2


def test_missing_work_never_created(prepared):
    state,_,sha,_,call,_=prepared
    def empty(message):
        if message['method']=='history':return {'records':[],'has_more':False}
        raise AssertionError('must not submit')
    with pytest.raises(ValueError,match='existing exact'):cli.apply(state,sha,True,empty)


def test_original_packet_edit_does_not_change_frozen_input(prepared):
    state,packet,sha,_,call,path=prepared
    path.write_text('{}')
    assert cli.apply(state,sha,True,call)['markdown_sha256']==packet['binding']['markdown_sha256']


@pytest.mark.parametrize('field,value',[('caller_uid',12345),('service_uid',996),('packet_sha256','e'*64),('extra',True)])
def test_mutated_configuration_refused_before_call(prepared,field,value):
    state,_,sha,_,_,_=prepared
    path=state/'configuration.json';config=d.read(path);path.unlink();config[field]=value;d.write(path,config)
    with pytest.raises(ValueError):cli.apply(state,sha,True,lambda _:pytest.fail('unexpected call'))


def test_frozen_packet_tamper_refused(prepared):
    state,_,sha,_,_,_=prepared
    path=state/'document/packet.json';saved=d.read(path);path.unlink();saved['packet']['markdown']+='changed';d.write(path,saved)
    with pytest.raises(ValueError):cli.apply(state,sha,True,lambda _:pytest.fail('unexpected call'))


def test_cli_missing_approval_is_sanitized(prepared,capsys):
    state,_,sha,_,_,_=prepared
    with pytest.raises(SystemExit):cli.main(['apply','--state',str(state),'--packet-sha256',sha])
    assert 'Preserve private state' in capsys.readouterr().err


def test_cli_inspect_and_status(prepared,capsys):
    state,_,_,_,_,path=prepared
    cli.main(['inspect','--packet',str(path)]);assert 'history_records_written' in capsys.readouterr().out
    cli.main(['status','--state',str(state)]);assert 'status_only' in capsys.readouterr().out
