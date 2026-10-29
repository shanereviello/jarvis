"""Whole-handoff initialization and visible pending managed-event delivery."""
import copy
import os
import pytest
from test_engineering_history_local import module
from test_history_managed_sync import linked,handoff
from test_history_managed_link import setup,exporter,j,fixtures
from jsonschema import ValidationError

sync=module('managed_sync');c=module('contract')


def test_initialize_from_complete_handoff_no_submission(linked,tmp_path):
    _,_,_,packet,work,history,call=linked;source=handoff(tmp_path/'input',[packet]);state=tmp_path/'new'
    def read_only(message):
        assert message['method']=='history';return call(message)
    result=sync.initialize_handoff(state,work,source,'/run/fixture.sock',os.getuid(),read_only)
    assert result['history_records_written'] is False and result['pages']==1
    assert result['capture_sha256']==sync.inspect(state,source)['capture_sha256']
    assert len(history.history()['records'])==1


def test_bad_handoff_refused_before_history_or_state(linked,tmp_path):
    _,_,_,packet,work,_,_=linked;source=handoff(tmp_path/'input',[packet]);(source/'packet-000.json').write_text('{}')
    state=tmp_path/'new'
    with pytest.raises((ValueError,ValidationError)):
        sync.initialize_handoff(state,work,source,'/run/fixture.sock',os.getuid(),lambda _:pytest.fail('no history call'))
    assert not state.exists()


def test_pending_lost_response_visible_without_claiming_receipt(linked,tmp_path):
    state,_,_,packet,_,history,call=linked;source=handoff(tmp_path/'input',[packet]);sha=sync.inspect(state,source)['capture_sha256']
    def lost(message):
        answer=call(message)
        if message['method']=='submit':raise OSError('lost after commit')
        return answer
    with pytest.raises(OSError):sync.apply(state,source,sha,lost)
    status=sync.status(state)
    assert len(history.history()['records'])==2 and status['completed_source_cursor']==0
    assert status['pending_captures']==[{'capture_sha256':sha,'state':'pending','pages':1,'source_cursor':1,'source_events':1,'saved_receipts':0}]
    sync.resume(state,sha,call)
    assert sync.status(state)['pending_captures']==[]
    assert len(history.history()['records'])==2


def test_pending_receipt_is_validated_not_just_counted(linked,tmp_path):
    state,_,_,packet,_,_,call=linked;source=handoff(tmp_path/'input',[packet]);sha=sync.inspect(state,source)['capture_sha256']
    with pytest.raises(OSError):sync.apply(state,source,sha,lambda m:call(m) if m['method']=='history' else (_ for _ in ()).throw(OSError('offline')))
    receipt=state/'captures'/('capture-'+sha)/'page-000/receipt-000.json';receipt.write_text('{}');receipt.chmod(0o600)
    with pytest.raises(ValueError):sync.status(state)


def test_pending_altered_frozen_input_refused(linked,tmp_path):
    state,_,_,packet,_,_,call=linked;source=handoff(tmp_path/'input',[packet]);sha=sync.inspect(state,source)['capture_sha256']
    with pytest.raises(OSError):sync.apply(state,source,sha,lambda m:call(m) if m['method']=='history' else (_ for _ in ()).throw(OSError('offline')))
    path=state/'captures'/('capture-'+sha)/'input.json';path.write_text('{}')
    with pytest.raises(ValueError):sync.status(state)


def test_incomplete_setup_visible_without_success(linked):
    state,*_=linked;directory=state/'captures'/('capture-'+'a'*64);directory.mkdir(mode=0o700)
    status=sync.status(state)
    assert status['pending_captures']==[{'capture_sha256':'a'*64,'state':'incomplete_local_setup'}]
    assert status['completed_captures']==0 and status['source_freshness']=='not_polled'


def test_cli_handoff_init_and_status(linked,tmp_path,monkeypatch,capsys):
    _,_,_,packet,work,_,call=linked;source=handoff(tmp_path/'input',[packet]);state=tmp_path/'new'
    path=tmp_path/'work.json';path.write_bytes(c.encoded(work));path.chmod(0o600)
    cli=module('managed_sync_cli');real=cli.local
    class Transport:
        @staticmethod
        def call(*args):return call(args[-1])
    monkeypatch.setattr(cli,'local',lambda name:Transport if name=='unix' else real(name))
    cli.main(['init','--state',str(state),'--work-request',str(path),'--handoff',str(source),'--socket','/run/fixture.sock','--service-uid',str(os.getuid())])
    assert 'capture_sha256' in capsys.readouterr().out
    cli.main(['status','--state',str(state)]);assert 'pending_captures' in capsys.readouterr().out
