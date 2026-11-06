"""Signed synthetic browser API; scoped project reads and no mutation routes."""
import json
from urllib.parse import urlencode

import pytest
from test_history_projects import projects, create, save, designate, assignment, read, P1, REPO, NON_GIT
from test_engineering_history_local import module, store
from test_history_web import web, key, access, client_call


@pytest.fixture
def project_reader(projects):
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
        return service.dispatch(1000, message)
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
