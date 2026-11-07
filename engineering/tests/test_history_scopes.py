"""Real disposable scope migration, history, snapshot and authorization checks."""
import copy
import json
import os
import sqlite3
import uuid

import pytest
from jsonschema import ValidationError
from test_engineering_history_local import module, request, note, store
from test_history_projects import projects, create, save, designate, assignment, read, state, REPO, NON_GIT, P1
from test_engineering_history_unix import env, running, rpc

sm = module('scopes')


def envelope(selected=REPO, revision=1, head=None, name='Jarvis display name'):
    return dict(contract='engineering-scope.v1', operation='scope.create' if revision == 1 else 'scope.revise',
                client_event_key=uuid.uuid4().hex, expected_head=head, scope=selected,
                source=dict(kind='agent_reported', namespace='fixture', id='reported-author'), occurred_at=None,
                body=dict(revision=revision, display_name=name, description='Scope description',
                          repository_url='https://example.test/owner/jarvis' if selected == REPO else None,
                          change_summary='Record scope revision'))


@pytest.fixture
def scopes(projects):
    value = sm.Scopes(projects.store)
    value.migrate(value.migration_plan()['expected_sha256'])
    return value


def test_v3_migration_preserves_all_old_tables_key_and_signed_snapshots(projects):
    create(projects); save(projects); designate(projects); assignment(projects)
    old = projects.read(REPO, dict(view='project', project_id=P1))
    tables = ('submissions', 'outbox', 'project_submissions', 'project_outbox', 'project_metadata')
    with projects.store.connection() as db:
        before = {table: db.execute('SELECT * FROM ' + table).fetchall() for table in tables}
    value = sm.Scopes(projects.store); plan = value.migration_plan()
    with pytest.raises(ValueError): value.migrate('0' * 64)
    value.migrate(plan['expected_sha256'])
    with projects.store.connection() as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 3
        assert {table: db.execute('SELECT * FROM ' + table).fetchall() for table in tables} == before
    value.submit(envelope())
    historical = projects.read(REPO, dict(view='project', project_id=P1, snapshot=old['snapshot']))
    assert historical['project'] == old['project']
    assert historical['scope_metadata']['recorded'] is False
    assert projects.read(REPO, dict(view='project', project_id=P1))['scope_metadata']['recorded'] is True


def test_migration_binds_project_state_and_rolls_back_ddl(projects, monkeypatch):
    value = sm.Scopes(projects.store); plan = value.migration_plan()
    create(projects)
    with pytest.raises(ValueError): value.migrate(plan['expected_sha256'])
    fresh = value.migration_plan(); monkeypatch.setattr(sm, 'DDL', sm.DDL + ('not valid SQL',))
    with pytest.raises(sqlite3.Error): value.migrate(fresh['expected_sha256'])
    with projects.store.connection() as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 2
        assert db.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='scope_submissions'").fetchone()[0] == 0


def test_scope_revisions_receipts_stale_heads_and_frozen_names(scopes, projects):
    first = envelope(); receipt = scopes.submit(first)['receipt']
    assert scopes.submit(first) == dict(inserted=False, receipt=receipt)
    frozen = projects.read(REPO, dict(view='scope'))
    second = envelope(revision=2, head=receipt['request_sha256'], name='Renamed Jarvis')
    scopes.submit(second)
    with pytest.raises(ValueError): scopes.submit(envelope(revision=2, head=receipt['request_sha256']))
    assert projects.read(REPO, dict(view='scope'))['metadata']['display_name'] == 'Renamed Jarvis'
    assert projects.read(REPO, dict(view='scope', snapshot=frozen['snapshot'])) == frozen
    assert projects.read(REPO, dict(view='scope', version=1))['metadata']['display_name'] == 'Jarvis display name'
    assert projects.read(REPO, dict(view='scope'))['total'] == 2


@pytest.mark.parametrize('url', ['https://user:secret@example.test/repo', 'https://example.test/repo?token=secret',
    'https://example.test/repo#secret', 'http://example.test/repo', 'javascript:alert(1)', 'https://example.test/a\nb'])
def test_scope_urls_are_credential_free(scopes, url):
    value = envelope(); value['body']['repository_url'] = url
    with pytest.raises((ValueError, ValidationError)): scopes.submit(value)


def test_non_git_url_and_new_category_refused(scopes):
    value = envelope(NON_GIT); value['body']['repository_url'] = 'https://example.test/repo'
    with pytest.raises(ValueError): scopes.submit(value)
    value = envelope(dict(kind='non_git', id='research'))
    with pytest.raises((ValueError, ValidationError)): scopes.submit(value)


def test_scope_counts_and_metadata_respect_grants(scopes, projects):
    scopes.submit(envelope()); first = projects.read(REPO, dict(view='scope'))
    scopes.submit(envelope(NON_GIT, name='Non-Git description'))
    assert projects.read(REPO, dict(view='scope')) == first
    policy = dict(contract='engineering-history-access.v2', principals=[dict(uid=1000,
        private_read=['jarvis'], write=[], category_read=[], category_write=[])])
    access = module('access').Access(projects.store, policy)
    result = access.dispatch(1000, dict(method='workspace_scopes'))
    assert result['scopes'] == [REPO] and len(result['scope_metadata']) == 1
    assert result['scope_metadata'][0]['display_name'] == 'Jarvis display name'
    with pytest.raises(ValueError): access.dispatch(1000, dict(method='scope_submit', request=envelope()))
    with pytest.raises(ValueError): access.dispatch(1000, dict(method='project_read', scope=NON_GIT, query=dict(view='scope')))
    token = dict(first['snapshot'], scope_sequence=0)
    with pytest.raises(ValueError): projects.read(REPO, dict(view='scope', snapshot=token))


def test_closeout_has_date_and_freezes_scope_revision(scopes, projects):
    scopes.submit(envelope()); create(projects); save(projects); designate(projects); assignment(projects)
    state(projects, 'completed', [dict(work_item_id='wrk_' + '1' * 32, disposition='deferred', reason='Recorded pending')])
    closeout = read(projects)['closeouts'][0]
    assert closeout['recorded_at'].endswith('Z') and closeout['writer_uid'] == os.getuid()
    first = projects.read(REPO, dict(view='scope'))['metadata']
    scopes.submit(envelope(revision=2, head=first['head'], name='Later name'))
    old = projects.read(REPO, dict(view='project', project_id=P1, closeout_sequence=closeout['sequence']))
    assert old['scope_metadata']['display_name'] == 'Jarvis display name'
    assert old['closeout']['recorded_at'] == closeout['recorded_at']


def test_scope_tables_are_immutable(scopes):
    scopes.submit(envelope())
    with scopes.store.connection() as db:
        for table in ('scope_submissions', 'scope_outbox'):
            for sql in ('DELETE FROM ' + table, 'UPDATE ' + table + ' SET request_sha256=request_sha256'):
                with pytest.raises(sqlite3.IntegrityError): db.execute(sql)


def test_actual_unix_scope_authoring_and_metadata_reads(env):
    _, store, _ = env; p = module('projects').Projects(store)
    p.migrate(p.migration_plan()['expected_sha256']); scopes = sm.Scopes(store)
    scopes.migrate(scopes.migration_plan()['expected_sha256'])
    policy = dict(contract='engineering-history-access.v2', principals=[dict(uid=os.getuid(),
        private_read=['jarvis'], write=['jarvis'], category_read=[], category_write=[])])
    with running(env, policy) as server:
        value = envelope(); first = rpc(server, dict(method='scope_submit', request=value))
        assert first['receipt']['peer_uid'] == os.getuid()
        assert rpc(server, dict(method='scope_submit', request=value))['receipt'] == first['receipt']
        assert rpc(server, dict(method='workspace_scopes'))['scope_metadata'][0]['recorded'] is True
        assert rpc(server, dict(method='project_read', scope=REPO, query=dict(view='scope')))['metadata']['revision'] == 1


def test_reported_outcomes_count_distinct_work_and_keep_old_revision(projects):
    create(projects); assignment(projects)
    old = projects.read(REPO, dict(view='work', work_id='wrk_' + '1' * 32))
    head = old['work_revision_sha256']
    projects.store.submit(request('outcome.record', 'finished-v1', head, dict(work_item_id='wrk_' + '1' * 32,
        work_revision_sha256=head, outcome='completed_claim', summary='Reported complete', references=[])))
    assert read(projects)['reported_outcome_counts']['completed_claim'] == 1
    revised = copy.deepcopy(old['work']); revised['revision'] = 2
    projects.store.submit(request('work.revise', 'revised-v2', head, revised))
    result = read(projects)
    assert result['work_count'] == 1 and result['reported_outcome_counts']['completed_claim'] == 0
    assert result['earlier_revision_outcome_count'] == 1
    item = projects.read(REPO, dict(view='works', project_id=P1))['items'][0]
    assert item['revision'] == 2 and item['outcome_revision'] == 1


def test_outcome_revision_resolves_each_work_in_a_mixed_history(projects):
    first_id, second_id = 'wrk_' + '1' * 32, 'wrk_' + '2' * 32
    first = projects.read(REPO, dict(view='work', work_id=first_id))
    head = first['work_revision_sha256']
    projects.store.submit(request('outcome.record', 'first-outcome', head, dict(work_item_id=first_id,
        work_revision_sha256=head, outcome='completed_claim', summary='First report', references=[])))
    second = copy.deepcopy(first['work']); second['work_item_id'] = second_id
    second_head = projects.store.submit(request('work.create', 'second-work', None, second))['receipt']['work_revision_sha256']
    projects.store.submit(request('outcome.record', 'second-outcome', second_head, dict(work_item_id=second_id,
        work_revision_sha256=second_head, outcome='partial', summary='Second report', references=[])))
    revised = copy.deepcopy(first['work']); revised['revision'] = 2
    projects.store.submit(request('work.revise', 'first-revision', head, revised))
    works = {item['work_item_id']: item for item in projects.read(REPO, dict(view='works'))['items']}
    assert works[first_id]['revision'] == 2 and works[first_id]['outcome_revision'] == 1
    assert works[second_id]['revision'] == 1 and works[second_id]['outcome_revision'] == 1


def test_scope_cli_exact_private_file_and_idempotency(scopes, tmp_path, capsys):
    cli = module('scope_cli'); path = tmp_path/'request.json'
    path.write_text(json.dumps(envelope())); path.chmod(0o600)
    args = ['submit', '--store', str(scopes.store.root), '--request', str(path)]
    cli.main(args); first = json.loads(capsys.readouterr().out)
    cli.main(args); second = json.loads(capsys.readouterr().out)
    assert first['receipt'] == second['receipt'] and second['inserted'] is False
