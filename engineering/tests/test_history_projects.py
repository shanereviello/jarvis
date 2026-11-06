"""Disposable v1/v2 stores: migration, design custody, membership and closeout."""
import copy
import json
import os
from concurrent.futures import ThreadPoolExecutor
import uuid

import pytest
from jsonschema import ValidationError
from test_engineering_history_local import module, request, store, note, document
from test_engineering_history_unix import env

pm = module('projects')
c = module('contract')
REPO = {'kind': 'repository', 'id': 'jarvis'}
NON_GIT = {'kind': 'non_git', 'id': 'jarvis-non-git'}
P1, P2 = 'prj_' + '1' * 32, 'prj_' + '2' * 32


@pytest.fixture
def projects(store):
    legacy = request()
    legacy['body']['repository_id'] = 'jarvis'
    store.submit(legacy)
    value = pm.Projects(store)
    value.migrate(value.migration_plan()['expected_sha256'])
    return value


def envelope(project_id, op, body, head=None, selected_scope=REPO):
    return dict(contract='engineering-project.v1', operation=op, client_event_key=uuid.uuid4().hex,
                expected_head=head, scope=selected_scope, project_id=project_id,
                source={'kind': 'human_reported', 'namespace': 'fixture', 'id': None}, occurred_at=None, body=body)


def create(projects, project_id=P1, selected_scope=REPO):
    return projects.submit(envelope(project_id, 'project.create', dict(revision=1, name='Recorded project',
        overview='Project grouping', intended_outcome='Preserve intent and design', in_scope='History',
        out_of_scope='Execution', owner=None, change_summary='Initial project'), selected_scope=selected_scope))


def read(projects, project_id=P1, selected_scope=REPO):
    return projects.read(selected_scope, {'view': 'project', 'project_id': project_id})['project']


def submit(projects, op, body, project_id=P1, selected_scope=REPO):
    return projects.submit(envelope(project_id, op, body, read(projects, project_id, selected_scope)['head'], selected_scope))


def save(projects, version=1, markdown='# Architecture\n\nOriginal design.\n', selected_scope=REPO):
    project = read(projects, selected_scope=selected_scope)
    previous = project['architecture'][-1] if project['architecture'] else None
    return submit(projects, 'architecture.save', dict(document_id='doc_' + '4' * 32, version=version,
        previous_sha256=previous['markdown_sha256'] if previous else None, title='Project architecture',
        change_summary='Recorded design ' + str(version), markdown=markdown, source_reference=None), selected_scope=selected_scope)


def designate(projects, version=1, selected_scope=REPO):
    doc = read(projects, selected_scope=selected_scope)['architecture'][version - 1]
    return submit(projects, 'architecture.designate', dict(version=version, markdown_sha256=doc['markdown_sha256'], reason='Selected design'), selected_scope=selected_scope)


def assignment(projects, work_id='wrk_' + '1' * 32, project_id=P1):
    result = projects.read(REPO, {'view': 'work', 'work_id': work_id})
    previous = result['assignment']
    old_id = previous['project_id'] if previous else None
    return submit(projects, 'membership.assign', dict(work_item_id=work_id,
        expected_assignment_sha256=previous['assignment_sha256'] if previous else None,
        expected_previous_project_head=read(projects, old_id)['head'] if old_id else None,
        architecture_version=read(projects, project_id)['governing_version'], reason='Explicit assignment'), project_id)


def state(projects, value, dispositions=None, selected_scope=REPO):
    return submit(projects, 'project.state', dict(state=value, reason='Operator records ' + value,
        baseline_omission_reason='Final commit unknown' if value == 'completed' and selected_scope == REPO else None,
        dispositions=dispositions or []), selected_scope=selected_scope)


def test_explicit_migration_preserves_legacy_bytes_and_receipts(store):
    store.submit(request())
    with store.connection() as db:
        before = db.execute('SELECT * FROM submissions').fetchall()
        pending = db.execute('SELECT * FROM outbox').fetchall()
    p = pm.Projects(store)
    plan = p.migration_plan()
    with pytest.raises(ValueError):
        p.migrate('0' * 64)
    assert p.migration_plan() == plan
    p.migrate(plan['expected_sha256'])
    with store.connection() as db:
        assert db.execute('SELECT * FROM submissions').fetchall() == before
        assert db.execute('SELECT * FROM outbox').fetchall() == pending
        assert db.execute('PRAGMA user_version').fetchone() == (2,)
    with pytest.raises(ValueError):
        p.migrate(plan['expected_sha256'])
    assert module('store').Store(store.root).history()['records'][0]['submission'] == request()


def test_migration_refuses_changed_source(store):
    p = pm.Projects(store)
    plan = p.migration_plan()
    store.submit(request())
    with pytest.raises(ValueError):
        p.migrate(plan['expected_sha256'])


def test_legacy_unassigned_visible_before_migration(store):
    store.submit(request())
    p = pm.Projects(store)
    assert p.read({'kind': 'repository', 'id': 'example'}, {'view': 'works', 'unassigned': True})['total'] == 1
    with pytest.raises(ValueError):
        create(p)


def test_idempotent_intake_and_conflicting_key(projects):
    request = envelope(P1, 'project.create', dict(revision=1, name='Name', overview='Overview',
        intended_outcome='Outcome', in_scope='Scope', out_of_scope='Exclusions', owner=None, change_summary='Created'))
    first = projects.submit(request, peer_uid=1000)
    assert projects.submit(request, peer_uid=1000) == {'inserted': False, 'receipt': first['receipt']}
    changed = copy.deepcopy(request)
    changed['body']['overview'] = 'Different'
    with pytest.raises(ValueError, match='idempotency'):
        projects.submit(changed, peer_uid=1000)


def test_atomic_reassignment_and_old_project_history(projects):
    create(projects)
    create(projects, P2)
    assignment(projects)
    assert read(projects)['work_count'] == 1
    assignment(projects, project_id=P2)
    assert read(projects)['work_count'] == 0 and read(projects, P2)['work_count'] == 1
    history = projects.read(REPO, {'view': 'history', 'project_id': P1})
    assert history['items'][0]['operation'] == 'membership.assign'
    a = projects.read(REPO, {'view': 'work', 'work_id': 'wrk_' + '1' * 32})['assignment']
    submit(projects, 'membership.remove', dict(work_item_id='wrk_' + '1' * 32,
        expected_assignment_sha256=a['assignment_sha256'], reason='Unassigned'), P2)
    assert projects.read(REPO, {'view': 'works', 'unassigned': True})['total'] == 1


def test_stale_concurrent_assignment_has_one_winner(projects):
    create(projects)
    head = read(projects)['head']
    def write(_):
        request = envelope(P1, 'membership.assign', dict(work_item_id='wrk_' + '1' * 32,
            expected_assignment_sha256=None, expected_previous_project_head=None, architecture_version=None,
            reason='Concurrent assignment'), head)
        try:
            projects.submit(request)
            return True
        except ValueError:
            return False
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(write, range(2))) == [False, True]


def test_document_drafts_governing_diff_and_work_design_pin(projects):
    create(projects)
    save(projects)
    assert read(projects)['governing_version'] is None
    designate(projects)
    assignment(projects)
    save(projects, 2, '# Architecture\n\nRevised design.\n')
    assert read(projects)['governing_version'] == 1
    designate(projects, 2)
    work = projects.read(REPO, {'view': 'work', 'work_id': 'wrk_' + '1' * 32})
    assert work['assignment']['architecture_version'] == 1
    old = projects.read(REPO, {'view': 'architecture', 'project_id': P1, 'version': 1})
    assert old['document']['markdown'] == '# Architecture\n\nOriginal design.\n'
    diff = projects.read(REPO, {'view': 'compare', 'project_id': P1, 'left': 1, 'right': 2})['diff']
    assert '-Original design.' in diff and '+Revised design.' in diff


def test_baseline_history_and_scope_are_immutable(projects):
    create(projects)
    receipt = submit(projects, 'baseline.record', dict(baseline_id='bas_' + '5' * 32, version=1,
        previous_sha256=None, commit='a' * 40, ref='main', label='Starting code', reason='Selected reference',
        source_reference=None, verified_at=None))['receipt']
    digest = receipt['effect']['baseline']['baseline_sha256']
    for role in ('starting', 'current'):
        submit(projects, 'baseline.select', dict(role=role, version=1, baseline_sha256=digest, reason='Selected baseline'))
    save(projects)
    submit(projects, 'baseline.record', dict(baseline_id='bas_' + '5' * 32, version=2,
        previous_sha256=digest, commit='b' * 40, ref='main', label='Later code', reason='New reference',
        source_reference=None, verified_at=None))
    assert read(projects)['architecture'][0]['baseline']['commit'] == 'a' * 40
    assert read(projects)['starting_baseline'] == 1


def test_closeout_pins_work_and_membership_after_later_notes(projects):
    create(projects)
    save(projects)
    designate(projects)
    assignment(projects)
    with pytest.raises(ValueError):
        state(projects, 'completed')
    state(projects, 'completed', [{'work_item_id': 'wrk_' + '1' * 32, 'disposition': 'deferred', 'reason': 'Explicit follow-up'}])
    original = read(projects)['closeouts'][0]
    query = {'view': 'works', 'project_id': P1, 'closeout_sequence': original['sequence']}
    frozen = projects.read(REPO, query)['items']
    head = projects.store.history()['records'][0]['receipt']['work_revision_sha256']
    projects.store.submit(note(head))
    assert projects.read(REPO, query)['items'] == frozen
    with pytest.raises(ValueError):
        save(projects, 2)
    state(projects, 'active')
    assert read(projects)['closeouts'][0] == original


def test_non_git_work_has_real_scope_and_architecture_without_commit(projects):
    work = request(key='non-git-work')
    work['contract'] = 'engineering-history.v2'
    work['body'].pop('repository_id')
    work['body'].update(scope=NON_GIT, work_item_id='wrk_' + '9' * 32, allowed_paths=[], baseline=None)
    projects.store.submit(work)
    create(projects, selected_scope=NON_GIT)
    save(projects, selected_scope=NON_GIT)
    designate(projects, selected_scope=NON_GIT)
    project = read(projects, selected_scope=NON_GIT)
    assert project['baseline_applicability'] == 'not_applicable'
    assert project['architecture'][0]['baseline'] is None
    state(projects, 'completed', selected_scope=NON_GIT)
    changed = copy.deepcopy(work)
    changed['body']['baseline'] = {'ref': 'main', 'commit': 'a' * 40}
    with pytest.raises(ValueError):
        c.validate(changed)
    changed = copy.deepcopy(work)
    changed['body']['scope']['id'] = 'research'
    with pytest.raises((ValueError, ValidationError)):
        c.validate(changed)


def test_non_git_work_documents_use_category_label(projects):
    work = request(key='non-git-work')
    work['contract'] = 'engineering-history.v2'
    work['body'].pop('repository_id')
    work['body'].update(scope=NON_GIT, work_item_id='wrk_' + '9' * 32, allowed_paths=[], baseline=None)
    head = projects.store.submit(work)['receipt']['work_revision_sha256']
    doc = document(head)
    doc['body']['work_item_id'] = work['body']['work_item_id']
    projects.store.submit(doc)
    raw, _ = projects.store.document(doc['body']['document_id'])
    assert b'non_git_category: "jarvis-non-git"' in raw


def test_scoped_access_revocation_and_snapshot_counts_do_not_leak(projects):
    create(projects)
    create(projects, P2, {'kind': 'repository', 'id': 'robot_ws'})
    policy = {'contract': 'engineering-history-access.v2', 'principals': [dict(uid=1000,
        private_read=['jarvis'], write=['jarvis'], category_read=[], category_write=[])]}
    access = module('access').Access(projects.store, policy)
    result = access.dispatch(1000, {'method': 'project_read', 'scope': REPO, 'query': {'view': 'projects'}})
    assert result['total'] == 1 and result['snapshot']['project_sequence'] == 1
    with pytest.raises(ValueError):
        access.dispatch(1000, {'method': 'project_read', 'scope': {'kind': 'repository', 'id': 'robot_ws'}, 'query': {'view': 'projects'}})
    with pytest.raises(ValueError):
        access.dispatch(1000, {'method': 'project_read', 'scope': NON_GIT, 'query': {'view': 'projects'}})
    with pytest.raises(ValueError):
        access.dispatch(1000, {'method': 'project_read', 'scope': REPO, 'query': {'view': 'project', 'project_id': P2}})


def test_snapshot_pages_stay_stable_during_new_appends(projects):
    create(projects)
    page = projects.read(REPO, {'view': 'projects'})
    create(projects, P2)
    assert projects.read(REPO, {'view': 'projects', 'snapshot': page['snapshot']}) == page


def test_snapshot_boundary_cannot_be_mixed_or_moved_between_scopes(projects):
    create(projects)
    token = projects.read(REPO, {'view': 'projects'})['snapshot']
    tampered = dict(token, work_sequence=0)
    with pytest.raises(ValueError, match='snapshot boundary changed'):
        projects.read(REPO, {'view': 'projects', 'snapshot': tampered})
    with pytest.raises(ValueError):
        projects.read(NON_GIT, {'view': 'projects', 'snapshot': token})


def test_migration_failure_rolls_back_all_added_tables(store, monkeypatch):
    p = pm.Projects(store)
    plan = p.migration_plan()
    monkeypatch.setattr(pm, 'DDL', (pm.DDL[0], 'INVALID SQL'))
    import sqlite3
    with pytest.raises(sqlite3.OperationalError):
        p.migrate(plan['expected_sha256'])
    assert p.migration_plan() == plan


def test_historical_project_name_does_not_follow_later_revision(projects):
    create(projects)
    save(projects)
    designate(projects)
    state(projects, 'completed')
    closeout = read(projects)['closeouts'][0]
    state(projects, 'active')
    original = read(projects)
    body = {k: original[k] for k in ('revision','name','overview','intended_outcome','in_scope','out_of_scope','owner','change_summary')}
    body.update(revision=2, name='Renamed after reopening')
    submit(projects, 'project.revise', body)
    historical = projects.read(REPO, {'view': 'project', 'project_id': P1, 'closeout_sequence': closeout['sequence']})
    assert historical['project']['name'] == 'Recorded project'
    assert historical['snapshot'] == closeout['snapshot']


def test_project_document_identity_cannot_alias_work_document(projects):
    head = projects.store.history()['records'][0]['receipt']['work_revision_sha256']
    projects.store.submit(document(head))
    create(projects)
    body = dict(document_id='doc_' + '2' * 32, version=1, previous_sha256=None,
        title='Conflicting identity', change_summary='Refused', markdown='# Different document\n', source_reference=None)
    with pytest.raises(ValueError, match='identity'):
        submit(projects, 'architecture.save', body)


def test_owner_cli_private_request_and_idempotent_receipt(projects, tmp_path):
    import subprocess, sys
    from pathlib import Path
    body = dict(revision=1, name='CLI project', overview='Explicit input', intended_outcome='Recorded receipt',
        in_scope='Private history', out_of_scope='Execution', owner=None, change_summary='Initial')
    path = tmp_path / 'request.json'
    path.write_bytes(c.encoded(envelope(P1, 'project.create', body)))
    path.chmod(0o600)
    script = Path(__file__).resolve().parents[1] / 'tools/rras_history/project_entry.py'
    command = [sys.executable, str(script), 'submit', '--store', str(projects.store.root), '--request', str(path)]
    first = json.loads(subprocess.run(command, check=True, capture_output=True).stdout)
    again = json.loads(subprocess.run(command, check=True, capture_output=True).stdout)
    assert first['inserted'] and not again['inserted'] and first['receipt'] == again['receipt']


def test_actual_unix_project_receipt_and_non_git_client(env):
    from test_engineering_history_unix import running, rpc
    _, store, client_state = env
    p = pm.Projects(store)
    p.migrate(p.migration_plan()['expected_sha256'])
    policy = dict(contract='engineering-history-access.v2', principals=[dict(uid=os.getuid(),
        private_read=['jarvis'], write=['jarvis'], category_read=['jarvis-non-git'], category_write=['jarvis-non-git'])])
    project_request = envelope(P1, 'project.create', dict(revision=1, name='Socket project', overview='Explicit socket intake',
        intended_outcome='Scoped reads', in_scope='History', out_of_scope='Execution', owner=None, change_summary='Initial'))
    with running(env, policy) as server:
        result = rpc(server, {'method': 'project_submit', 'request': project_request})
        assert result['receipt']['peer_uid'] == os.getuid()
        assert rpc(server, {'method': 'project_submit', 'request': project_request})['receipt'] == result['receipt']
        assert rpc(server, {'method': 'project_read', 'scope': REPO, 'query': {'view': 'projects'}})['total'] == 1
        work = request(key='socket-non-git')
        work['contract'] = 'engineering-history.v2'
        work['body'].pop('repository_id')
        work['body'].update(scope=NON_GIT, allowed_paths=[])
        client = module('interactive').Client(client_state, service_socket=server.path, service_uid=os.getuid(), create=True)
        client.enqueue('start', 'non-git-start', work)
        assert client.flush()['delivered_now'] == 2
        assert rpc(server, {'method': 'project_read', 'scope': NON_GIT, 'query': {'view': 'works'}})['total'] == 1


def test_project_tables_refuse_update_delete(projects):
    create(projects)
    import sqlite3
    with projects.store.connection() as db:
        for statement in ('DELETE FROM project_submissions', 'UPDATE project_submissions SET client_key="x"',
                          'DELETE FROM project_outbox', 'UPDATE project_outbox SET request_sha256="x"'):
            with pytest.raises(sqlite3.IntegrityError):
                db.execute(statement)
