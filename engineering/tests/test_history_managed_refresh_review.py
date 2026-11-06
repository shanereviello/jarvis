"""Private human-readable refresh previews without intake or authority."""
import copy
import hashlib
import json
import os
import stat
import pytest
from jsonschema import ValidationError
from test_engineering_history_local import module
from test_history_managed_sync import linked,handoff
from test_history_managed_link import setup,exporter,j,fixtures

sync=module('managed_sync');c=module('contract')


def snapshot(root):
    return {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}


def test_review_is_deterministic_private_and_leaves_sources_unchanged(linked,tmp_path):
    state,_,_,packet,_,history,_=linked;source=handoff(tmp_path/'input',[packet])
    before=snapshot(state),snapshot(source),history.history()
    outputs=[]
    for name in ('review-one','review-two'):
        target=tmp_path/name;result=sync.refresh_review(state,source,target)
        report=json.loads((target/'review.json').read_text());raw=(target/'review.md').read_bytes()
        assert result['capture_sha256']==sync.inspect(state,source)['capture_sha256']
        assert result['markdown_sha256']==hashlib.sha256(raw).hexdigest()
        assert result['review_json_sha256']==hashlib.sha256((target/'review.json').read_bytes()).hexdigest()
        assert report['new_since_completed_events']==1 and report['previously_completed_events']==0
        assert report['apply_authorized'] is False and report['source_authenticated'] is False
        assert report['source_freshness']=='not_polled' and report['release_status']=='not_inferred'
        assert stat.S_IMODE(target.stat().st_mode)==0o700
        assert all(stat.S_IMODE(p.stat().st_mode)==0o600 for p in target.iterdir())
        outputs.append(((target/'review.json').read_bytes(),raw))
    assert outputs[0]==outputs[1]
    assert (snapshot(state),snapshot(source),history.history())==before


def test_overlap_review_only_lists_new_claims_and_replay_lists_none(linked,tmp_path):
    state,journal,rows,packet,_,_,call=linked;first=handoff(tmp_path/'first',[packet])
    sync.apply(state,first,sync.inspect(state,first)['capture_sha256'],call)
    journal.append([fixtures.next_event(rows)])
    fresh=exporter.export(journal.root,packet['journal_id'],packet['work']['record_sha256'])
    source=handoff(tmp_path/'fresh',[fresh]);target=tmp_path/'review'
    sync.refresh_review(state,source,target);report=json.loads((target/'review.json').read_text())
    assert report['source_events']==2 and report['previously_completed_events']==1
    assert report['new_since_completed_events']==1
    assert report['new_since_completed_event_claims'][0]['event_id']==fresh['facts'][1]['event_id']
    sync.apply(state,source,sync.inspect(state,source)['capture_sha256'],call)
    again=tmp_path/'review-replay';sync.refresh_review(state,source,again)
    report=json.loads((again/'review.json').read_text());assert report['new_since_completed_events']==0
    with pytest.raises(ValueError,match='regresses'):sync.refresh_review(state,first,tmp_path/'regressed')
    assert not (tmp_path/'regressed').exists()


def test_lost_response_is_not_presented_as_new_server_rows(linked,tmp_path):
    state,_,_,packet,_,history,call=linked;source=handoff(tmp_path/'input',[packet])
    def lost(message):
        answer=call(message)
        if message['method']=='submit':raise OSError('response lost after commit')
        return answer
    with pytest.raises(OSError):sync.apply(state,source,sync.inspect(state,source)['capture_sha256'],lost)
    before=history.history();target=tmp_path/'review';sync.refresh_review(state,source,target)
    report=json.loads((target/'review.json').read_text())
    assert report['new_since_completed_events']==1
    assert report['pending_captures'][0]['saved_receipts']==0
    assert 'not absent from the server' in (target/'review.md').read_text()
    assert history.history()==before


@pytest.mark.parametrize('change',['packet','receipt','scope'])
def test_bad_input_or_completed_receipt_refuses_before_output(linked,tmp_path,change):
    state,_,_,packet,_,_,call=linked;source=handoff(tmp_path/'input',[packet])
    if change=='packet':(source/'packet-000.json').write_text('{}')
    elif change=='scope':
        value=copy.deepcopy(packet);value['work']['requested_paths']=['different.py']
        source=handoff(tmp_path/'wrong-scope',[value])
    else:
        sha=sync.inspect(state,source)['capture_sha256'];sync.apply(state,source,sha,call)
        p=state/'captures'/('capture-'+sha)/'page-000/receipt-000.json';p.write_text('{}')
    target=tmp_path/'review'
    with pytest.raises((ValueError,ValidationError)):sync.refresh_review(state,source,target)
    assert not target.exists()


@pytest.mark.parametrize('where',['state','handoff','existing','symlink','public_parent'])
def test_destination_cannot_overwrite_or_write_into_sources(linked,tmp_path,where):
    state,_,_,packet,_,_,_=linked;source=handoff(tmp_path/'input',[packet])
    target=state/'review' if where=='state' else source/'review' if where=='handoff' else tmp_path/'review'
    if where=='existing':target.mkdir(mode=0o700);(target/'sentinel').write_text('retain')
    if where=='symlink':target.symlink_to(source,target_is_directory=True)
    if where=='public_parent':
        parent=tmp_path/'public';parent.mkdir(mode=0o755);target=parent/'review'
        # This fixture must stay public even when an earlier CLI test or the
        # caller has selected a restrictive process umask.
        parent.chmod(0o755)
    before=snapshot(state),snapshot(source)
    with pytest.raises((ValueError,OSError)):sync.refresh_review(state,source,target)
    assert (snapshot(state),snapshot(source))==before
    if where=='existing':assert (target/'sentinel').read_text()=='retain'


def test_cli_review_does_not_contact_transport(linked,tmp_path,monkeypatch,capsys):
    state,_,_,packet,_,_,_=linked;source=handoff(tmp_path/'input',[packet]);cli=module('managed_sync_cli');original=cli.local
    class Offline:
        @staticmethod
        def call(*args):pytest.fail('review must not contact the service')
    monkeypatch.setattr(cli,'local',lambda name:Offline if name=='unix' else original(name))
    cli.main(['review','--state',str(state),'--handoff',str(source),'--destination',str(tmp_path/'review')])
    result=json.loads(capsys.readouterr().out);assert result['prepared'] is True and result['apply_authorized'] is False


def test_review_escapes_markdown_and_html_in_source_claims(linked,tmp_path,monkeypatch):
    state,_,_,packet,_,_,_=linked;source=handoff(tmp_path/'input',[packet]);original=sync.configuration
    def changed(root):
        value=original(root);value['binding']=dict(value['binding']);value['binding']['synthetic_display']='```<script>&'
        return value
    # Keep binding validation intact, then exercise only rendering with this
    # otherwise inaccessible adversarial display value in the validated bundle.
    config=changed(state);bundle=sync.capture(original(state),source)
    monkeypatch.setattr(sync,'configuration',lambda _:config)
    monkeypatch.setattr(sync,'capture',lambda *args:bundle)
    target=tmp_path/'review';sync.refresh_review(state,source,target)
    raw=(target/'review.md').read_text()
    assert raw.count('```')==2 and '<script>' not in raw
    shown=raw.split('```json\n',1)[1].split('\n```',1)[0]
    assert json.loads(shown)['binding']['synthetic_display']=='```<script>&'
