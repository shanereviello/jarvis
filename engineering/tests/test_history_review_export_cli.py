"""Explicit reusable export front end preserves the historical custody boundary."""
import pytest
from test_engineering_history_local import module,DOC
from test_history_managed_review import inputs

cli=module('review_export_cli');link=module('review_document_link')


@pytest.fixture
def producer(inputs,monkeypatch):
    packet=link.build({'work_request':inputs[2],'package':module('managed_review').build(*inputs,DOC)})
    calls=[]
    class Producer:
        def snapshot(self,*args,**kwargs):calls.append(('snapshot',args,kwargs));return packet
        def handoff(self,*args,**kwargs):calls.append(('handoff',args,kwargs));return {'phase':'private_review_document_handoff_complete'}
    real=cli.local
    monkeypatch.setattr(cli,'local',lambda name:Producer() if name=='review_document_export' else real(name))
    return packet,calls


def run(command,**kwargs):return cli.run(command,'/protected','a'*64,'/original','b'*64,**kwargs)


def test_inspect_returns_hashes_without_narrative_or_handoff(producer):
    packet,calls=producer
    result=run('inspect',approve_private_read=True)
    assert result['packet_sha256']==link.inspect(packet)['packet_sha256']
    assert result['mutations'] is False and 'markdown' not in result
    assert [x[0] for x in calls]==['snapshot']


def test_inspection_requires_explicit_private_read(producer):
    _,calls=producer
    with pytest.raises(ValueError):run('inspect')
    assert not calls


@pytest.mark.parametrize('kwargs',[{}, {'approve_private_export':True},
 {'approve_private_export':True,'packet_sha256':'f'*64,'export_id':'../escape'}])
def test_export_approval_and_identity_before_any_read(producer,kwargs):
    _,calls=producer
    with pytest.raises(ValueError):run('export',**kwargs)
    assert not calls


def test_changed_packet_refuses_before_handoff(producer):
    _,calls=producer
    with pytest.raises(ValueError,match='reviewed packet'):run('export',approve_private_export=True,packet_sha256='f'*64,export_id='c'*32)
    assert [x[0] for x in calls]==['snapshot']


def test_export_uses_only_exact_reviewed_snapshot(producer):
    packet,calls=producer
    run('export',approve_private_export=True,packet_sha256=link.inspect(packet)['packet_sha256'],export_id='c'*32)
    assert calls[-1]==('handoff',('c'*32,packet),{'approve_private_export':True})


def test_cli_refusal_does_not_print_private_error(monkeypatch,capsys):
    def fail(**kwargs):raise ValueError('private narrative sentinel')
    monkeypatch.setattr(cli,'run',fail)
    with pytest.raises(SystemExit):cli.main(['inspect','--state','/p','--review-id','a'*64,'--source-release','/s','--source-manifest-sha256','b'*64,'--approve-private-read'])
    err=capsys.readouterr().err
    assert 'private narrative sentinel' not in err and 'Preserve protected evidence' in err
