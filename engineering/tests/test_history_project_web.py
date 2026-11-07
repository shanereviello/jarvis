"""Signed synthetic browser API; scoped project reads and no mutation routes."""
import json
from itertools import permutations
from urllib.parse import urlencode

import pytest
from test_history_projects import projects, create, save, designate, assignment, read, P1, REPO, NON_GIT
from test_engineering_history_local import module, store
from test_history_web import web, key, access, client_call


@pytest.fixture
def project_reader(projects):
    from test_history_scopes import envelope
    scopes = module('scopes').Scopes(projects.store)
    scopes.migrate(scopes.migration_plan()['expected_sha256'])
    scopes.submit(envelope())
    scopes.submit(envelope(NON_GIT, name='Jarvis non-Git planning'))
    create(projects)
    save(projects)
    designate(projects)
    assignment(projects)
    policy = {'contract': 'engineering-history-access.v2', 'principals': [dict(uid=1000,
        private_read=['jarvis'], write=[], category_read=['jarvis-non-git'], category_write=[])]}
    service = module('access').Access(projects.store, policy)
    calls = []
    def call(message):
        calls.append(message)
        # The real Unix transport sorts JSON keys in both directions. Preserve
        # that boundary here so browser/API fixtures consume actual wire order.
        contract = module('contract')
        request = contract.decode(contract.encoded(message))
        return contract.decode(contract.encoded(service.dispatch(1000, request)), max_bytes=2 * 1024 * 1024)
    reader = web('history').Reader(['jarvis'], call, ['jarvis-non-git'])
    reader.calls = calls
    return reader


def url(view, **query):
    return '/api/workspace/' + view + '?' + urlencode(dict(scope_kind='repository', scope_id='jarvis', **query))


def test_scopes_and_complete_project_reader_path(project_reader, key):
    app = web('app').create_app(project_reader, access(key))
    scopes = client_call(app, key, '/api/workspace/scopes').json()
    assert scopes['scopes'] == [REPO, NON_GIT]
    result = client_call(app, key, url('projects')).json()
    assert result['total'] == 1
    project = client_call(app, key, url('project', project_id=P1)).json()['project']
    assert project['governing_version'] == 1 and project['work_count'] == 1
    document = client_call(app, key, url('architecture', project_id=P1, version=1)).json()
    assert document['digest_verified'] is True and document['document']['markdown'].startswith('# Architecture')
    work = client_call(app, key, url('work', work_id='wrk_' + '1' * 32)).json()
    assert work['assignment']['architecture_version'] == 1 and work['timeline']
    assert set(c['method'] for c in project_reader.calls) == {'workspace_scopes', 'project_read'}


@pytest.mark.parametrize('view,query', [
    ('works', {'project_id': P1}),
    ('architecture', {'project_id': P1, 'version': 1}),
    ('history', {'project_id': P1}),
    ('work', {'work_id': 'wrk_' + '1' * 32}),
    ('compare', {'project_id': P1, 'left': 1, 'right': 1}),
])
def test_project_tabs_reuse_actual_wire_snapshot(project_reader, key, view, query):
    app = web('app').create_app(project_reader, access(key))
    snapshot = client_call(app, key, url('project', project_id=P1)).json()['snapshot']
    assert list(snapshot) == ['project_sequence', 'scope_sequence', 'sha256', 'work_sequence']
    # JSON.stringify keeps the order received from the service, without spaces.
    token = json.dumps(snapshot, separators=(',', ':'))
    result = client_call(app, key, url(view, snapshot=token, **query))
    assert result.status_code == 200
    assert result.json()['snapshot'] == snapshot


def test_snapshot_member_order_and_whitespace_do_not_change_token(project_reader, key):
    app = web('app').create_app(project_reader, access(key))
    snapshot = client_call(app, key, url('project', project_id=P1)).json()['snapshot']
    for members in permutations(snapshot.items()):
        for separators in ((',', ':'), (', ', ': ')):
            token = json.dumps(dict(members), separators=separators)
            result = client_call(app, key, url('works', project_id=P1, snapshot=token))
            assert result.status_code == 200
            assert result.json()['snapshot'] == snapshot


@pytest.mark.parametrize('token', [
    'null', '[]', '0',
    '{"work_sequence":true,"project_sequence":0}',
    '{"work_sequence":1.0,"project_sequence":0}',
    '{"work_sequence":-1,"project_sequence":0}',
    '{"work_sequence":10001,"project_sequence":0}',
    '{"work_sequence":0,"project_sequence":0,"unexpected":0}',
    '{"work_sequence":0,"project_sequence":0,"work_sequence":1}',
    '{"work_sequence":0,"project_sequence":0,"sha256":"x"}',
    '{"work_sequence":0,"project_sequence":0,"sha256":null}',
    '{"work_sequence":0,"project_sequence":0,"sha256":"' + 'a' * 64 + '","sha256":"' + 'b' * 64 + '"}',
    ' ' * 257,
])
def test_malformed_snapshot_fails_before_service(project_reader, key, token):
    app = web('app').create_app(project_reader, access(key))
    result = client_call(app, key, url('works', project_id=P1, snapshot=token))
    assert result.status_code == 400
    assert project_reader.calls == []


@pytest.mark.parametrize('change', ['missing_mac', 'wrong_mac', 'future_boundary', 'other_scope'])
def test_snapshot_authentication_stays_in_service(project_reader, key, change):
    app = web('app').create_app(project_reader, access(key))
    snapshot = client_call(app, key, url('project', project_id=P1)).json()['snapshot']
    if change == 'missing_mac':
        del snapshot['sha256']
        snapshot.pop('scope_sequence', None)
    elif change == 'wrong_mac':
        snapshot['sha256'] = '0' * 64
    elif change == 'future_boundary':
        snapshot['work_sequence'] += 1
    else:
        snapshot = project_reader.workspace(NON_GIT, {'view': 'projects'})['snapshot']
    result = client_call(app, key, url('works', project_id=P1, snapshot=json.dumps(snapshot)))
    assert result.status_code == 503


def test_legacy_unsigned_snapshot_still_parses():
    assert web('app').snapshot_token('{"project_sequence": 0, "work_sequence": 1}') == {
        'project_sequence': 0, 'work_sequence': 1}


def test_scope_metadata_history_uses_the_same_signed_read_boundary(project_reader, key):
    app = web('app').create_app(project_reader, access(key))
    info = client_call(app, key, '/api/workspace/scopes').json()
    assert [m['scope'] for m in info['scope_metadata']] == [REPO, NON_GIT]
    result = client_call(app, key, url('scope')).json()
    assert result['metadata']['display_name'] == 'Jarvis display name'
    assert result['total'] == 1 and result['snapshot']['scope_sequence'] == 1
    assert client_call(app, key, url('scope', version=1, snapshot=json.dumps(result['snapshot']))).status_code == 200


@pytest.mark.parametrize('extra', ['scope_sequence', 'project_sequence', 'work_sequence'])
def test_three_stream_snapshot_rejects_boolean_sequences(project_reader, key, extra):
    app = web('app').create_app(project_reader, access(key))
    token = dict(work_sequence=0, project_sequence=0, scope_sequence=0, sha256='a' * 64)
    token[extra] = True
    assert client_call(app, key, url('scope', snapshot=json.dumps(token))).status_code == 400
    assert project_reader.calls == []


@pytest.mark.parametrize('view', ['projects', 'project', 'architecture', 'compare', 'works', 'work', 'history'])
def test_unauthorized_scope_never_calls_service(project_reader, key, view):
    app = web('app').create_app(project_reader, access(key))
    result = client_call(app, key, '/api/workspace/' + view + '?scope_kind=repository&scope_id=other')
    assert result.status_code == 503 and project_reader.calls == []


@pytest.mark.parametrize('method', ['POST', 'PUT', 'PATCH', 'DELETE'])
def test_project_web_is_read_only(project_reader, key, method):
    app = web('app').create_app(project_reader, access(key))
    result = client_call(app, key, url('project_submit'), method)
    assert result.status_code == 405 and project_reader.calls == []


def test_exact_architecture_tamper_refused(project_reader):
    original = project_reader.call
    def changed(message):
        result = original(message)
        if message['query']['view'] == 'architecture':
            result['document']['markdown'] += 'changed'
        return result
    project_reader.call = changed
    with pytest.raises(ValueError):
        project_reader.workspace(REPO, {'view': 'architecture', 'project_id': P1, 'version': 1})


@pytest.mark.parametrize('extra', ['archived=maybe', 'version=true', 'offset=-1', 'scope_id=other', 'unexpected=1',
                                  'snapshot=%7B%22work_sequence%22%3Atrue%7D'])
def test_invalid_project_queries_fail_before_reads(project_reader, key, extra):
    app = web('app').create_app(project_reader, access(key))
    result = client_call(app, key, url('projects') + '&' + extra)
    assert result.status_code == 400 and project_reader.calls == []


def test_non_git_only_reader_and_v2_config_are_explicit(project_reader):
    history = web('history')
    assert history.Reader([], project_reader.call, ['jarvis-non-git']).workspace_scopes()['scopes'] == [NON_GIT]
    assert history.Reader(['jarvis'], project_reader.call).workspace_scopes()['scopes'] == [REPO]
    from test_history_web_entry import config
    entry = web('entry')
    value = config()
    value.update(contract='engineering-history-web.v2', categories=['jarvis-non-git'])
    assert entry.configuration(value) == value
    value['categories'] = ['research']
    with pytest.raises(ValueError):
        entry.configuration(value)


def test_category_grants_required_even_for_known_non_git_work(projects):
    create(projects, selected_scope=NON_GIT)
    policy = {'contract': 'engineering-history-access.v1', 'principals': [dict(uid=1000, private_read=['jarvis'], write=['jarvis'])]}
    boundary = module('access').Access(projects.store, policy)
    with pytest.raises(ValueError):
        boundary.dispatch(1000, {'method': 'project_read', 'scope': NON_GIT, 'query': {'view': 'projects'}})
