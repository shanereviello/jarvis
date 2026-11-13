import importlib.util
import os
from pathlib import Path
import pytest
from test_reporting_onboarding_drafts import uid,REPO

path=Path(__file__).resolve().parents[1]/'tools/rras_reporting/onboarding_operator_entry.py'
spec=importlib.util.spec_from_file_location('operator_entry_fixture',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def sample(tmp_path):
    return dict(operator_uid=os.getuid(),operator_gid=os.getgid(),planning_peer_uid=61181,browser_peer_uid=61182,history_uid=61183,
        history_socket=str(tmp_path/'history'/'service.sock'),review_socket=str(tmp_path/'review'/'service.sock'),
        browser_socket=str(tmp_path/'browser'/'service.sock'),organization_id=uid(1),app_user_id=uid(2),team_id=uid(3),human_ids=[uid(4)],scopes=[REPO],
        reader_origin_url='http://127.0.0.1:5678/webhook/fixture',reader_issue_url='http://127.0.0.1:5678/webhook/fixture',
        comment_url='http://127.0.0.1:5678/webhook/fixture',access=dict(issuer='https://fixture.cloudflareaccess.com',audience='fixture',email='owner@example.test',origin='https://fixture.example.test'))


def test_private_initialization_and_exclusive_lock(tmp_path):
    state=tmp_path/'operator';assert module.initialize(state)==dict(initialized=True,listener_started=False,execution_authorized=False)
    with module.journal(state) as connection:
        with connection() as db:assert db.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0]==3
        with pytest.raises(BlockingIOError):
            with module.journal(state):pass
    with pytest.raises(ValueError):module.initialize(state)


def test_configuration_requires_separate_peers_and_socket_directories(tmp_path):
    config=sample(tmp_path)
    assert module.configuration(config,os.getuid(),os.getgid())==config
    with pytest.raises(ValueError):module.configuration(dict(config,browser_peer_uid=config['planning_peer_uid']),os.getuid(),os.getgid())
    with pytest.raises(ValueError):module.configuration(dict(config,browser_socket=config['review_socket']),os.getuid(),os.getgid())
    with pytest.raises(ValueError):module.configuration(dict(config,unexpected=True),os.getuid(),os.getgid())


def test_optional_admission_requires_dedicated_socket_and_fixed_issue_reader(tmp_path):
    config=sample(tmp_path)
    config['admission']=dict(socket=str(tmp_path/'admission'/'service.sock'),
        issue_url='http://127.0.0.1:5678/webhook/rras-operator-issue-'+config['app_user_id'])
    assert module.configuration(config,os.getuid(),os.getgid()) == config
    with pytest.raises(ValueError):
        module.configuration(dict(config,admission=dict(config['admission'],socket=config['review_socket'])),os.getuid(),os.getgid())
    with pytest.raises(ValueError):
        module.configuration(dict(config,admission=dict(config['admission'],issue_url='http://external.example/issue')),os.getuid(),os.getgid())


def test_jarvis_review_has_separate_identity_and_private_routes(tmp_path):
    config=sample(tmp_path);app=uid(8)
    config['jarvis_review']=dict(socket=str(tmp_path/'jarvis-review'/'service.sock'),peer_uid=61184,app_user_id=app,
        origin_url='http://127.0.0.1:5678/webhook/rras-jarvis-planning-origin-'+app,
        issue_url='http://127.0.0.1:5678/webhook/rras-jarvis-planning-issue-'+app,scope_path=str(tmp_path/'scopes.json'))
    assert module.configuration(config,os.getuid(),os.getgid())==config
    for field,value in [('peer_uid',config['planning_peer_uid']),('app_user_id',config['app_user_id']),('socket',config['review_socket'])]:
        with pytest.raises(ValueError):module.configuration(dict(config,jarvis_review=dict(config['jarvis_review'],**{field:value})),os.getuid(),os.getgid())
