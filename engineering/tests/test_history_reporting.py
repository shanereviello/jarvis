"""Disposable v4 metadata migration, exact scoped pins and signed four-stream views."""
import copy
import os
import sqlite3
import uuid
import pytest
from test_engineering_history_local import module, store
from test_history_projects import projects, create, save, designate, assignment, read, state, REPO, NON_GIT, P1
from test_history_scopes import envelope as scope_envelope
from test_history_reporting_contract import request as contract_request
from test_engineering_history_unix import env, running, rpc

rm = module('reporting'); c = module('contract')
WORK = 'wrk_' + '1' * 32


def ready(projects):
    create(projects); save(projects); designate(projects); assignment(projects)
    scopes = module('scopes').Scopes(projects.store); scopes.migrate(scopes.migration_plan()['expected_sha256'])
    return scopes


@pytest.fixture
def reporting(projects):
    ready(projects)
    value = rm.Reporting(projects.store); value.migrate(value.migration_plan()['expected_sha256'])
    return value


def request(projects, operation='mapping.record', *, project_mapping=False):
    value = contract_request(operation); value['client_event_key'] = uuid.uuid4().hex
    project = read(projects); work = projects.read(REPO, dict(view='work', work_id=WORK))
    doc = project['architecture'][0]
    value['context'] = dict(project_id=P1, architecture={k: doc[k] for k in ('document_id', 'version', 'markdown_sha256')},
        work=dict(work_item_id=WORK, work_revision_sha256=work['work_revision_sha256'], assignment_sha256=work['assignment']['assignment_sha256']))
    if project_mapping:
        value['context']['work'] = None
        value['body'].update(mapping_id='map_' + '2' * 32, kind='project', plan_id=None,
                             linear=dict(value['body']['linear'], issue_id=None))
    return value


def project_map(reporting, projects): return reporting.submit(request(projects, project_mapping=True))


def test_imported_linear_decision_requires_explicit_separate_designation(reporting, projects):
    """A decision observation retains its source but cannot designate a draft."""
    save(projects, 2, '# Candidate architecture\n\nSynthetic review text.\n')
    project = read(projects)
    candidate = project['architecture'][-1]
    decision = request(projects, 'decision.observe')
    decision['context']['architecture'] = {k: candidate[k] for k in ('document_id', 'version', 'markdown_sha256')}
    decision['context']['work'] = None
    decision['source'] = dict(kind='imported', namespace='linear_comment', id='synthetic-comment')
    decision['body'].update(kind='architecture', state='approved', attribution='imported_source',
        attributed_author=dict(role='human', runtime='linear', source_actor_id=str(uuid.UUID(int=8))),
        source_reference=dict(namespace='linear_comment', id='synthetic-comment', sha256='7' * 64),
        decision_text='Synthetic operator approval of architecture version 2, SHA-256 ' + candidate['markdown_sha256'])
    receipt = reporting.submit(decision)
    assert reporting.submit(decision) == dict(inserted=False, receipt=receipt['receipt'])
    assert read(projects)['governing_version'] == 1
    assert receipt['receipt']['authority_granted'] is False
    designate(projects, 2)
    assert read(projects)['governing_version'] == 2
    with reporting.store.connection() as db:
        stored = [(r, rcpt) for r, rcpt in reporting.events(db) if r['operation'] == 'decision.observe']
    assert len(stored) == 1
    assert stored[0][0]['body']['source_reference'] == decision['body']['source_reference']
    assert stored[0][0]['body']['attribution'] == 'imported_source'


def test_upgrade_preserves_prior_bytes_schema_key_and_old_signed_views(projects):
    create(projects); save(projects); designate(projects); assignment(projects)
    old2 = projects.read(REPO, dict(view='project', project_id=P1))
    scopes = module('scopes').Scopes(projects.store); scopes.migrate(scopes.migration_plan()['expected_sha256'])
    scopes.submit(scope_envelope())
    old3 = projects.read(REPO, dict(view='project', project_id=P1))
    tables = ['submissions', 'outbox', 'project_submissions', 'project_outbox', 'project_metadata', 'scope_submissions', 'scope_outbox']
    with projects.store.connection() as db:
        before = {name: db.execute('SELECT * FROM ' + name).fetchall() for name in tables}
        ddl = db.execute("SELECT name,sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY name").fetchall()
    reporting = rm.Reporting(projects.store); plan = reporting.migration_plan()
    with pytest.raises(ValueError): reporting.migrate('0' * 64)
    reporting.migrate(plan['expected_sha256']); project_map(reporting, projects)
    with projects.store.connection() as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 4
        assert {name: db.execute('SELECT * FROM ' + name).fetchall() for name in tables} == before
        after = dict(db.execute("SELECT name,sql FROM sqlite_master WHERE sql IS NOT NULL"))
        assert all(after[name] == sql for name, sql in ddl)
    for old in (old2, old3):
        assert projects.read(REPO, dict(view='project', project_id=P1, snapshot=old['snapshot'])) == old
        records = projects.read(REPO, dict(view='reporting', project_id=P1, snapshot=old['snapshot']))
        assert records['available'] is False and records['total'] == 0
    current = projects.read(REPO, dict(view='project', project_id=P1))
    assert current['snapshot']['reporting_sequence'] == 1 and current['project']['reporting']['available']
    assert current['project']['reporting']['execution_mapping_count'] == 0


def test_upgrade_plan_binds_scope_bytes_and_ddl_failure_rolls_back(projects, monkeypatch):
    scopes = ready(projects); reporting = rm.Reporting(projects.store); plan = reporting.migration_plan()
    scopes.submit(scope_envelope())
    with pytest.raises(ValueError): reporting.migrate(plan['expected_sha256'])
    plan = reporting.migration_plan(); monkeypatch.setattr(rm, 'DDL', rm.DDL + ('invalid SQL',))
    with pytest.raises(sqlite3.Error): reporting.migrate(plan['expected_sha256'])
    with projects.store.connection() as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 3
        assert not db.execute("SELECT name FROM sqlite_master WHERE name='reporting_submissions'").fetchone()


def test_exact_receipt_replay_and_immutable_metadata_outbox(reporting, projects):
    project_map(reporting, projects)
    value = request(projects); first = reporting.submit(value)
    assert reporting.submit(value) == dict(inserted=False, receipt=first['receipt'])
    value['body']['reason'] += ' changed'
    with pytest.raises(ValueError): reporting.submit(value)
    with reporting.store.connection() as db:
        for sql in ['UPDATE reporting_submissions SET request_sha256=\'changed\'', 'DELETE FROM reporting_submissions',
                    'UPDATE reporting_outbox SET request_sha256=\'changed\'', 'DELETE FROM reporting_outbox']:
            with pytest.raises(sqlite3.IntegrityError): db.execute(sql)
        assert db.execute('SELECT COUNT(*) FROM reporting_outbox').fetchone()[0] == 2
    assert first['receipt']['authority_granted'] is False


@pytest.mark.parametrize('field', ['project', 'architecture', 'work', 'assignment', 'scope'])
def test_unknown_or_cross_scope_context_never_creates_reporting_row(reporting, projects, field):
    value = request(projects, 'checkpoint.report')
    if field == 'project': value['context']['project_id'] = 'prj_' + '9' * 32
    elif field == 'architecture': value['context']['architecture']['markdown_sha256'] = '9' * 64
    elif field == 'work': value['context']['work']['work_revision_sha256'] = '9' * 64
    elif field == 'assignment': value['context']['work']['assignment_sha256'] = '9' * 64
    else: value['scope']['id'] = 'other'
    with pytest.raises(ValueError): reporting.submit(value)
    with reporting.store.connection() as db: assert reporting.events(db) == []


def test_project_binding_and_duplicate_execution_work_are_checked(reporting, projects):
    with pytest.raises(ValueError): reporting.submit(request(projects))
    project_map(reporting, projects); value = request(projects)
    value['body']['linear']['organization_id'] = str(uuid.uuid4())
    with pytest.raises(ValueError): reporting.submit(value)
    first = reporting.submit(request(projects)); duplicate = request(projects)
    duplicate['body']['mapping_id'] = 'map_' + '3' * 32
    with pytest.raises(ValueError): reporting.submit(duplicate)
    second = request(projects); second['body'].update(version=2, previous_sha256=first['receipt']['request_sha256'])
    second['expected_head'] = first['receipt']['request_sha256']; second['body']['reason'] = 'Append corrected display reference'
    reporting.submit(second)
    current = projects.read(REPO, dict(view='project', project_id=P1))['project']['reporting']
    assert current['execution_mapping_count'] == 1 and current['record_count'] == 3


def test_four_stream_snapshot_and_closeout_do_not_join_later_reporting(reporting, projects):
    project_map(reporting, projects)
    first = projects.read(REPO, dict(view='project', project_id=P1))
    state(projects, 'active')
    closed = state(projects, 'completed', [dict(work_item_id=WORK, disposition='deferred', reason='Source remains unfinished')])['receipt']
    closeout = projects.read(REPO, dict(view='project', project_id=P1, closeout_sequence=closed['sequence']))
    closed_work = projects.read(REPO, dict(view='works', project_id=P1, closeout_sequence=closed['sequence']))
    reporting.submit(request(projects, 'checkpoint.report'))
    assert projects.read(REPO, dict(view='project', project_id=P1, snapshot=first['snapshot'])) == first
    assert projects.read(REPO, dict(view='project', project_id=P1, closeout_sequence=closed['sequence'])) == closeout
    assert projects.read(REPO, dict(view='works', project_id=P1, closeout_sequence=closed['sequence'])) == closed_work
    bad = dict(first['snapshot'], reporting_sequence=2)
    with pytest.raises(ValueError): projects.read(REPO, dict(view='reporting', snapshot=bad))


def test_attempt_retry_and_handoff_states_keep_actual_runtime_and_context(reporting, projects):
    value = request(projects, 'attempt.record'); first = reporting.submit(value)['receipt']
    value['client_event_key'] = uuid.uuid4().hex; value['expected_head'] = first['request_sha256']
    value['body'].update(version=2, previous_sha256=first['request_sha256'], phase='failed')
    second = reporting.submit(value)['receipt']
    value['client_event_key'] = uuid.uuid4().hex; value['expected_head'] = second['request_sha256']
    value['body'].update(version=3, previous_sha256=second['request_sha256'], phase='started')
    with pytest.raises(ValueError): reporting.submit(value)
    handoff = request(projects, 'handoff.record'); first = reporting.submit(handoff)['receipt']
    handoff['client_event_key'] = uuid.uuid4().hex; handoff['expected_head'] = first['request_sha256']
    handoff['body'].update(version=2, previous_sha256=first['request_sha256'], state='completed', target_session=dict(namespace='fixture', id='recipient'))
    with pytest.raises(ValueError): reporting.submit(handoff)
    handoff['body']['state'] = 'acknowledged'; reporting.submit(handoff)


def test_reader_denial_scope_filtering_and_unverified_artifact_refusal(reporting, projects):
    project_map(reporting, projects)
    access = module('access').Access(reporting.store, dict(contract='engineering-history-access.v2', principals=[
        dict(uid=1000, private_read=['jarvis'], write=[], category_read=[], category_write=[]),
        dict(uid=1001, private_read=['other'], write=['other'], category_read=[], category_write=[])]))
    message = dict(method='reporting_submit', request=request(projects, 'checkpoint.report'))
    with pytest.raises(ValueError): access.dispatch(1000, message)
    with pytest.raises(ValueError): access.dispatch(1001, message)
    with pytest.raises(ValueError): access.dispatch(1001, dict(method='project_read', scope=REPO, query=dict(view='reporting')))
    other = access.dispatch(1001, dict(method='project_read', scope=dict(kind='repository', id='other'), query=dict(view='reporting')))
    assert other['total'] == 0 and other['snapshot']['reporting_sequence'] == 0
    with pytest.raises(ValueError, match='private evidence'): reporting.submit(request(projects, 'artifact.record'))
    scope_result = module('scopes').Scopes(reporting.store).submit(scope_envelope())
    assert scope_result['receipt']['revision'] == 1


def test_actual_unix_reporting_receipt_restart_and_write_revocation(env):
    from test_engineering_history_local import request as work_request
    root, store, _ = env
    value = work_request(); value['body']['repository_id'] = 'jarvis'; store.submit(value)
    projects = module('projects').Projects(store); projects.migrate(projects.migration_plan()['expected_sha256'])
    ready(projects); reporting = rm.Reporting(store); reporting.migrate(reporting.migration_plan()['expected_sha256'])
    grants = dict(contract='engineering-history-access.v1', principals=[dict(uid=os.getuid(), private_read=['jarvis'], write=['jarvis'])])
    message = dict(method='reporting_submit', request=request(projects, project_mapping=True))
    with running(env, grants) as server:
        receipt = rpc(server, message)['receipt']
        assert receipt['peer_uid'] == os.getuid() and receipt['authority_granted'] is False
        result = rpc(server, dict(method='project_read', scope=REPO, query=dict(view='reporting')))
        assert result['total'] == 1 and result['items'][0]['receipt'] == receipt
    with running(env, grants) as server: assert rpc(server, message) == dict(inserted=False, receipt=receipt)
    grants['principals'][0]['write'] = []
    with running(env, grants) as server:
        with pytest.raises(ValueError): rpc(server, message)


def test_reporting_cli_uses_exact_private_inputs_and_owner_reviewed_plan(projects, tmp_path, capsys):
    ready(projects); cli = module('reporting_cli')
    args = ['--store', str(projects.store.root)]
    cli.main(['migration-plan', *args]); plan = __import__('json').loads(capsys.readouterr().out)
    cli.main(['migrate', *args, '--expected-sha256', plan['expected_sha256']])
    assert __import__('json').loads(capsys.readouterr().out)['migrated']
    value = request(projects, project_mapping=True); path = tmp_path / 'request.json'
    path.write_bytes(c.encoded(value)); path.chmod(0o600)
    cli.main(['submit', *args, '--request', str(path)])
    assert __import__('json').loads(capsys.readouterr().out)['inserted']
    query = dict(scope=REPO, query=dict(view='reporting', project_id=P1))
    path.write_bytes(c.encoded(query)); cli.main(['read', *args, '--request', str(path)])
    assert __import__('json').loads(capsys.readouterr().out)['total'] == 1
    with pytest.raises(SystemExit):
        cli.main(['migrate', '--service-socket', str(tmp_path / 'missing.sock'), '--service-uid', '995', '--expected-sha256', plan['expected_sha256']])
