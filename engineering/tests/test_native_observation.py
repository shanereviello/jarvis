"""Bounded native snapshot inspection and real journal integration; no live board."""
import ast
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from test_workflow_finish import case
import test_managed_events as managed

SCHEMA='''CREATE TABLE tasks(id TEXT PRIMARY KEY,status TEXT,assignee TEXT,workspace_path TEXT,current_run_id INTEGER,completed_at INTEGER,worker_pid INTEGER,claim_lock TEXT,claim_expires INTEGER);
CREATE TABLE task_runs(id INTEGER PRIMARY KEY,task_id TEXT,profile TEXT,status TEXT,outcome TEXT,started_at INTEGER,ended_at INTEGER,worker_pid INTEGER,claim_lock TEXT,claim_expires INTEGER);'''


def create_board(path,c,schema=SCHEMA):
    with sqlite3.connect(path) as db:
        db.executescript(schema)
        columns={r[1] for r in db.execute('PRAGMA table_info(tasks)')}
        fields={'id':'t_finish','status':'done','assignee':'rras-engineering','workspace_path':c.evidence['workspace'],'completed_at':101}
        if 'title' in columns:fields.update(title='PRIVATE_BOARD_TEXT',created_at=90)
        db.execute('INSERT INTO tasks ('+','.join(fields)+') VALUES ('+','.join('?' for _ in fields)+')',list(fields.values()))
        db.execute('INSERT INTO task_runs(id,task_id,profile,status,outcome,started_at,ended_at) VALUES (1,?,?,?,?,?,?)',('t_finish','rras-engineering','done','completed',100,102))
    return path


@pytest.fixture
def observation(case):
    c=case;c.capture();m=managed.module('native_observation');board=create_board(c.x.root/'source-board.sqlite3',c)
    actual=m.local;worker=SimpleNamespace(worker_bytes=lambda path,limit:board.read_bytes())
    source=m.SOURCE.read_bytes() if m.SOURCE.is_file() else b'synthetic native schema pin fixture'
    reader=SimpleNamespace(root_bytes=lambda path,limit:source if Path(path)==m.SOURCE else Path(path).read_bytes())
    modules={'workflow_finish':c.f,'publication_capture':worker,'publication_custody':reader,'approved_launch':c.x.l,'managed_events':c.x.e}
    expected=m.SOURCE_SHA256 if m.SOURCE.is_file() else c.x.a.digest(source)
    with patch.object(m,'SOURCE_SHA256',expected),patch.object(m,'local',side_effect=lambda name:modules.get(name) or actual(name)):
        def capture(out):
            with patch.object(m.os,'getuid',return_value=0),patch.object(m.os,'geteuid',return_value=0):return m.capture(c.custody,out)
        def record(out):
            with patch.object(m.os,'getuid',return_value=0),patch.object(m.os,'geteuid',return_value=0):return m.record(c.custody,out)
        yield SimpleNamespace(m=m,c=c,board=board,capture=capture,record=record)


def inspect(o):return o.m.inspect_snapshot(o.board,o.c.host,o.c.evidence,o.c.context)
def mutate(o,sql,args=()):
    with sqlite3.connect(o.board) as db:db.execute(sql,args)


def test_direct_snapshot_observation_is_not_authenticated_success(observation):
    o=observation;out=o.c.x.root/'observation';original=o.board.read_bytes()
    assert o.capture(out)['stored_state']=='completed';assert not o.record(out)['task_success_established']
    event=o.c.x.events()[-1];assert event['event_type']=='artifact.recorded' and event['provenance']['kind']=='observed'
    assert o.c.x.store.status()['work_items'][0]['attempts'][0]['terminal_claim']['provenance']=='imported'
    count=len(o.c.x.events());o.record(out);assert len(o.c.x.events())==count
    assert o.board.read_bytes()==original


def test_incomplete_native_ownership_does_not_promote_success(observation):
    o=observation;mutate(o,'UPDATE tasks SET current_run_id=1')
    facts=inspect(o);assert facts['stored_state']=='incomplete' and not facts['ownership_fields_clear']
    out=o.c.x.root/'observation';o.capture(out);o.record(out)
    assert o.c.x.events()[-1]['outcome']=='uncertain'


def test_database_disagreement_is_retained_as_uncertain(observation):
    o=observation;mutate(o,"UPDATE tasks SET status='blocked',completed_at=NULL")
    mutate(o,"UPDATE task_runs SET status='failed',outcome='gave_up'")
    facts=inspect(o);assert facts['stored_state']=='failed' and not facts['agrees_with_captured_wait_report']
    out=o.c.x.root/'observation';o.capture(out);o.record(out);assert o.c.x.events()[-1]['outcome']=='uncertain'


@pytest.mark.parametrize('sql',["UPDATE tasks SET assignee='other'","UPDATE task_runs SET task_id='t_other'","UPDATE task_runs SET profile='other'","UPDATE tasks SET workspace_path='/wrong'","UPDATE task_runs SET id=2","UPDATE task_runs SET status='UNKNOWN_PRIVATE_STATUS'","UPDATE task_runs SET ended_at=99","UPDATE tasks SET completed_at=103"])
def test_mismatched_task_run_profile_status_time_refused(observation,sql):
    mutate(observation,sql)
    with pytest.raises(ValueError):inspect(observation)


def test_additional_native_attempt_is_not_adopted(observation):
    o=observation;mutate(o,"INSERT INTO task_runs(id,task_id,profile,status,started_at) VALUES(2,'t_finish','rras-engineering','running',103)")
    with pytest.raises(ValueError):inspect(o)


def test_sqlite_view_cannot_impersonate_task_table(observation):
    o=observation
    with sqlite3.connect(o.board) as db:db.executescript('ALTER TABLE tasks RENAME TO old_tasks;CREATE VIEW tasks AS SELECT * FROM old_tasks;')
    with pytest.raises(ValueError):inspect(o)


def test_corrupt_database_preserves_failed_capture(observation):
    o=observation;o.board.write_bytes(b'not a database');out=o.c.x.root/'partial'
    with pytest.raises(sqlite3.DatabaseError):o.capture(out)
    assert (out/'board.sqlite3').read_bytes()==b'not a database' and not (out/'observation.json').exists()


def test_nonempty_wal_refused_without_native_checkpoint(observation):
    o=observation;sidecar=Path(o.c.context['board']+'-wal');sidecar.parent.mkdir(parents=True);sidecar.write_bytes(b'pending')
    original=o.m.local;reader=SimpleNamespace(worker_bytes=lambda path,limit:b'pending')
    out=o.c.x.root/'blocked'
    with patch.object(o.m,'local',side_effect=lambda name:reader if name=='publication_capture' else original(name)),pytest.raises(ValueError):o.capture(out)
    assert sidecar.read_bytes()==b'pending' and not out.exists()


def test_active_worker_slot_refused_before_read(observation):
    o=observation;out=o.c.x.root/'blocked'
    with patch.object(o.c.x.l,'slot',side_effect=ValueError('fixture busy')),pytest.raises(ValueError):o.capture(out)
    assert not out.exists()


def test_tampered_snapshot_refused_before_journal(observation):
    o=observation;out=o.c.x.root/'observation';o.capture(out);(out/'board.sqlite3').write_bytes(b'changed')
    count=len(o.c.x.events())
    with pytest.raises(ValueError):o.record(out)
    assert len(o.c.x.events())==count


def test_projection_omits_snapshot_fields_and_private_board_text(observation):
    o=observation;out=o.c.x.root/'observation';o.capture(out);o.record(out)
    view=o.c.x.root/'view.json';o.c.x.store.publish_jarvis(view,o.c.x.work['work_item_id']);raw=view.read_bytes()
    assert b'PRIVATE_BOARD_TEXT' not in raw and str(o.c.x.root).encode() not in raw and b'rras-engineering' not in raw


def test_actual_pinned_native_schema_snapshot_is_compatible(observation):
    o=observation
    if not o.m.SOURCE.is_file():pytest.skip('optional pinned native installation absent')
    assert o.c.x.a.digest(o.m.SOURCE.read_bytes())==o.m.SOURCE_SHA256
    tree=ast.parse(o.m.SOURCE.read_text())
    schema=next(n.value.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='SCHEMA_SQL' for t in n.targets))
    other=o.c.x.root/'actual-schema.sqlite3';create_board(other,o.c,schema)
    facts=o.m.inspect_snapshot(other,o.c.host,o.c.evidence,o.c.context)
    assert facts['stored_state']=='completed' and facts['agrees_with_captured_wait_report']


def test_changed_native_source_pin_refused_before_capture(observation):
    o=observation;out=o.c.x.root/'refused'
    with patch.object(o.m,'SOURCE_SHA256','0'*64),pytest.raises(ValueError):o.capture(out)
    assert not out.exists()


def test_native_journal_write_failure_replays_without_duplicate_claim(observation):
    o=observation;out=o.c.x.root/'observation';o.capture(out);store=o.c.x.store;original=store.append;failures=[]
    def append(*args,**kwargs):
        transition=kwargs.get('transition')
        if transition and transition[0]['actor']['id']=='native-state-observer' and not failures:
            failures.append(True);raise OSError('fixture disk failure')
        return original(*args,**kwargs)
    with patch.object(o.c.x.e,'journal',return_value=store),patch.object(store,'append',side_effect=append):
        with pytest.raises(OSError):o.record(out)
        o.record(out)
    assert len([e for e in o.c.x.events() if e['actor']['id']=='native-state-observer'])==1
