"""Selected-source bounds and opt-in pinned SpecStory execution on fake history."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
from types import SimpleNamespace
import pytest

ROOT=Path(__file__).resolve().parents[1]/'tools/rras_reporting'
def module(name):
    spec=importlib.util.spec_from_file_location('collectors_test_'+name,ROOT/(name+'.py'))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
m=module('capture_collectors');intake=module('capture_intake');fixtures=module('capture_evaluation')


def test_source_authorization_is_required_before_opening_any_source(tmp_path):
    spool=intake.Spool(tmp_path/'spool',create=True)
    with pytest.raises(ValueError,match='authorization'):
        m.collect_codex(spool,source='/not-opened',session=fixtures.SESSION,binary='/not-opened',
            scope=dict(kind='repository',id='jarvis'),context=None,authorization_reference='')


@pytest.mark.parametrize('value',[None,'invalid','2026-11-07T12:00:00.123456789Z'])
def test_unknown_source_times_remain_unknown(value):assert m.source_time(value) is None


def test_source_time_normalizes_known_offset_without_using_import_clock():
    assert m.source_time('2026-11-07T07:00:00-05:00')=='2026-11-07T12:00:00Z'


@pytest.fixture
def binary(tmp_path):
    supplied=os.environ.get('SHRR_SPECSTORY_FIXTURE_BINARY')
    if not supplied:pytest.skip('opt-in already reviewed local collector binary required; no download')
    # Only the public binary is copied; no real collector home or source history.
    dest=tmp_path/'specstory';shutil.copyfile(supplied,dest);dest.chmod(0o700)
    assert hashlib.sha256(dest.read_bytes()).hexdigest()==m.SPECSTORY_SHA256
    return dest


@pytest.mark.parametrize('style',['legacy','thread-items','response-only'])
def test_actual_pinned_collector_reads_only_selected_synthetic_source(tmp_path,binary,style):
    spool=intake.Spool(tmp_path/'spool',create=True);worktree=tmp_path/'worker';worktree.mkdir()
    source=tmp_path/'selected.jsonl';rows=fixtures.events(worktree,style)
    rows.append(dict(type='response_item',timestamp='2026-11-07T12:00:03Z',payload=dict(
        type='message',role='assistant',channel='analysis',content=[dict(type='output_text',
            text='EXCLUDED-PRIVATE-ANALYSIS-FIXTURE-CONTENT-DO-NOT-EXPORT')])))
    raw=b''.join((json.dumps(x)+'\n').encode() for x in rows);source.write_bytes(raw);source.chmod(0o600)
    args=dict(source=str(source),session=fixtures.SESSION,binary=binary,scope=dict(kind='repository',id='jarvis'),
        context=None,authorization_reference='synthetic fixture only; no real sessions')
    result=m.collect_codex(spool,**args)
    assert result['models_started']==0 and result['collection_scope']=='explicit_session_only'
    assert source.read_bytes()==raw
    with spool.connection() as db:item=db.execute("SELECT * FROM items WHERE kind='artifact'").fetchone()
    export=(spool.exports/item['export_sha256']).read_text()
    assert 'EXCLUDED-PRIVATE-ANALYSIS-FIXTURE-CONTENT-DO-NOT-EXPORT' not in export
    if style=='response-only':assert fixtures.PROMPT not in export and fixtures.ANSWER not in export
    else:assert fixtures.PROMPT in export and fixtures.ANSWER in export
    assert m.collect_codex(spool,**args)['changed'] is False
    shutil.rmtree(worktree)
    assert (spool.exports/item['export_sha256']).exists()
    assert not list(spool.root.glob('collector-*'))


class NativeReader:
    def __init__(self):self.reads=[]
    def get_session(self,identifier):
        self.reads.append(('session',identifier));return dict(id=identifier,title='Selected',started_at=1794052800,last_active=1794052900)
    def get_compression_lineage(self,identifier):return ['selected-parent',identifier]
    def get_messages(self,identifier,**options):
        self.reads.append(('messages',identifier,options))
        return [dict(role='user',content='Visible request'),dict(role='assistant',content='Visible result',reasoning='EXCLUDED-FIELD'),
            dict(role='assistant',channel='analysis',content='EXCLUDED-CHANNEL'),dict(role='system',content='EXCLUDED-SYSTEM')]


def test_hermes_reader_is_selected_bounded_and_never_constructed():
    db=NativeReader()
    with pytest.raises(ValueError):m.selected_hermes(db,'selected','')
    assert not db.reads
    result=m.selected_hermes(db,'selected','fixture permission')
    assert result['lineage_session_ids']==['selected-parent','selected']
    reads=[x for x in db.reads if x[0]=='messages']
    assert [x[1] for x in reads]==['selected-parent','selected']
    assert all(x[2]['include_compacted'] is True and x[2]['limit']<=10001 for x in reads)
    db.get_compression_lineage=lambda _:['unrelated']
    with pytest.raises(ValueError,match='lineage'):m.selected_hermes(db,'selected','fixture permission')


def test_hermes_linear_alias_is_exact_and_never_a_path_or_prefix():
    db=NativeReader();alias='linear:00000000-0000-0000-0000-000000000001:00000000-0000-0000-0000-000000000005'
    assert m.selected_hermes(db,alias,'synthetic selected alias')['id']==alias
    assert any(row[1]==alias for row in db.reads)
    for identifier in ('../selected','/selected','selected*','selected?','selected\n',None):
        with pytest.raises(ValueError):m.selected_hermes(db,identifier,'synthetic invalid selection')


def test_hermes_native_redaction_then_owned_redaction_and_dedup(tmp_path,monkeypatch):
    spool=intake.Spool(tmp_path/'spool',create=True);source=tmp_path/'native.py'
    source.write_text('# synthetic reviewed exporter fixture');source.chmod(0o600)
    monkeypatch.setattr(m,'HERMES_EXPORTER_SHA256',hashlib.sha256(source.read_bytes()).hexdigest())
    calls=[]
    def redact(value):calls.append('native_redact');return value
    def render(value):
        calls.append('render');text=json.dumps(value)
        assert not any(x in text for x in ('EXCLUDED-FIELD','EXCLUDED-CHANNEL','EXCLUDED-SYSTEM'))
        return text+'\nAuthorization: Bearer synthetic-sensitive-header'
    native=SimpleNamespace(EXPORTER_VERSION='synthetic native v1',redact_session_data=redact,render_session_markdown=render)
    monkeypatch.setattr(m,'native_exporter',lambda _:native)
    snapshot=m.selected_hermes(NativeReader(),'selected','fixture permission')
    args=dict(snapshot=snapshot,exporter=source,scope=dict(kind='repository',id='jarvis'),context=None,
        authorization_reference='synthetic fixture only')
    result=m.collect_hermes(spool,**args)
    assert result['models_started']==0 and result['visible_messages']==4 and result['excluded_messages']==4
    assert calls==['native_redact','render']
    with spool.connection() as db:row=db.execute("SELECT * FROM items WHERE kind='artifact'").fetchone()
    text=(spool.exports/row['export_sha256']).read_text()
    assert 'Visible request' in text and 'Visible result' in text and 'synthetic-sensitive-header' not in text
    assert m.collect_hermes(spool,**args)['changed'] is False
    assert calls==['native_redact','render']


def test_multiple_native_segments_keep_separate_artifacts_and_session_identity(tmp_path,binary):
    spool=intake.Spool(tmp_path/'spool',create=True);worktree=tmp_path/'worker';worktree.mkdir()
    source=tmp_path/'selected.jsonl';rows=fixtures.events(worktree,'legacy')
    source.write_text(''.join(json.dumps(row)+'\n' for row in rows));source.chmod(0o600)
    args=dict(source=str(source),session=fixtures.SESSION,binary=binary,scope=dict(kind='repository',id='jarvis'),
        context=None,authorization_reference='synthetic fixture only')
    for segment in ('first','second'):
        assert m.collect_codex(spool,source_segment=segment,**args)['changed']
        assert not m.collect_codex(spool,source_segment=segment,**args)['changed']
    with spool.connection() as db:
        items=db.execute("SELECT request,artifact FROM items WHERE kind='artifact' ORDER BY sequence").fetchall()
    assert len(items)==2 and len({item['artifact'] for item in items})==2
    records=[spool.c.decode(item['request']) for item in items]
    assert records[0]['body']['session']==records[1]['body']['session']
    assert [r['body']['source_range']['start'] for r in records]==['segment:first:byte:0','segment:second:byte:0']
    assert all(r['body']['version']==1 for r in records)
    with source.open('a') as stream:
        stream.write(json.dumps(dict(type='event_msg',timestamp='2026-11-07T12:00:05Z',
            payload=dict(type='user_message',message='A synthetic appended exchange'))) + '\n')
    assert m.collect_codex(spool,source_segment='first',**args)['changed']
    with spool.connection() as db:
        item=db.execute("SELECT request,artifact FROM items WHERE kind='artifact' ORDER BY sequence DESC LIMIT 1").fetchone()
    latest=spool.c.decode(item['request'])
    assert item['artifact']==items[0]['artifact'] and latest['body']['version']==2
    assert not any('prefix shortened' in gap for gap in latest['body']['gaps'])
