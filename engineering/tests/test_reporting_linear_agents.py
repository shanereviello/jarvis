"""Model-free signed webhook, actual SQLite custody/replay and role-isolation tests."""
import copy
import hashlib
import hmac
import importlib.util
import json
from pathlib import Path
import sqlite3
import uuid

import pytest

ROOT = Path(__file__).resolve().parents[1]

def module(name):
    spec = importlib.util.spec_from_file_location('reporting_test_' + name, ROOT / 'tools/rras_reporting' / (name + '.py'))
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value); return value

m = module('linear_agents')
setup = module('linear_setup')
NOW = 1794067200

def ident(n): return str(uuid.UUID(int=n))

@pytest.fixture
def config(tmp_path):
    agents = {}
    for n, name in enumerate(['jarvis', 'codex'], 1):
        secret = tmp_path / (name + '-webhook'); secret.write_bytes((name * 12).encode()); secret.chmod(0o600)
        token = tmp_path / (name + '-token'); token.write_text('synthetic-' + name); token.chmod(0o600)
        agents[name] = dict(app_user_id=ident(n), oauth_client_id=ident(n + 2),
            webhook_secret_file=str(secret), access_token_file=str(token))
    binding = dict(project_id='prj_' + '1' * 32, work_id='wrk_' + '2' * 32, work_revision_sha256='3' * 64,
        architecture_version=3, architecture_sha256='4' * 64, plan_id='SHRR-03')
    return dict(contract='linear-agent-policy.v1', organization_id=ident(5), agents=agents, issues={ident(6): binding})

@pytest.fixture
def inbox(tmp_path, config): return m.Inbox(tmp_path / 'inbox', config, create=True)

def event(config, agent='codex', action='created', session=7):
    selected = config['agents'][agent]
    value = dict(type='AgentSessionEvent', action=action, appUserId=selected['app_user_id'],
        oauthClientId=selected['oauth_client_id'], organizationId=config['organization_id'], webhookTimestamp=NOW * 1000,
        agentSession=dict(id=ident(session), appUserId=selected['app_user_id'], organizationId=config['organization_id'],
            issueId=ident(6), creatorId=ident(20)), promptContext='Synthetic operator request to ' + agent)
    if action == 'prompted':
        value['agentActivity'] = dict(id=ident(8), agentSessionId=ident(session), userId=ident(20),
            content=dict(type='prompt', body='Synthetic direct architecture decision; retain the actual human source.'))
    return value

def signed(config, body, agent='codex', delivery=100):
    raw = m.encoded(body)
    secret = Path(config['agents'][agent]['webhook_secret_file']).read_bytes()
    return raw, {'Linear-Signature': hmac.new(secret, raw, hashlib.sha256).hexdigest(), 'Linear-Delivery': ident(delivery)}

def receive(inbox, config, body=None, agent='codex', delivery=100):
    raw, headers = signed(config, body or event(config, agent), agent, delivery)
    return inbox.receive(agent, raw, headers, now=NOW)

def test_codex_operates_without_jarvis_credential_access(inbox, config):
    Path(config['agents']['jarvis']['webhook_secret_file']).unlink()
    result = receive(inbox, config)
    assert result['inserted'] and result['agent'] == 'codex'
    messages = inbox.messages('codex')
    assert len(messages) == 1 and not inbox.messages('jarvis')
    assert messages[0]['agent'] == 'codex' and messages[0]['execution_authorized'] is False
    assert messages[0]['human_approval_inferred'] is False


def test_direct_followup_and_elicitation_have_same_work_and_codex_actor(inbox, config):
    receive(inbox, config)
    receive(inbox, config, event(config, action='prompted'), delivery=101)
    messages = inbox.messages('codex')
    assert len(messages) == 2 and messages[0]['binding'] == messages[1]['binding']
    inbox.bind_runtime('codex', ident(7), 'synthetic-codex-native-session')
    activity = inbox.activity('codex', ident(7), 'architecture-question', 'elicitation', 'Review exact architecture digest ' + '4' * 64)
    assert activity['variables']['input']['agentSessionId'] == ident(7)
    assert activity['variables']['input']['content']['type'] == 'elicitation'
    assert messages[1]['source_actor_id'] == ident(20)


def test_two_agents_do_not_receive_one_anothers_messages(inbox, config):
    receive(inbox, config, agent='jarvis')
    receive(inbox, config, agent='codex')
    assert inbox.messages('jarvis')[0]['app_user_id'] != inbox.messages('codex')[0]['app_user_id']
    assert inbox.messages('codex')[0]['message'].endswith('codex')
    assert inbox.messages('jarvis')[0]['message'].endswith('jarvis')


def test_repeat_delivery_and_new_delivery_id_reuse_source(inbox, config):
    first = receive(inbox, config)
    assert receive(inbox, config)['sequence'] == first['sequence']
    assert receive(inbox, config, delivery=101)['inserted'] is False
    assert len(inbox.messages('codex')) == 1
    reopened = m.Inbox(inbox.root, config)
    assert reopened.messages('codex') == inbox.messages('codex')


@pytest.mark.parametrize('change', ['signature', 'organization', 'client', 'app', 'session_app', 'session_org', 'issue', 'stale', 'future', 'action', 'event_type'])
def test_bad_or_cross_scope_events_never_enter_inbox(inbox, config, change):
    body = event(config)
    if change == 'organization': body['organizationId'] = ident(90)
    elif change == 'client': body['oauthClientId'] = config['agents']['jarvis']['oauth_client_id']
    elif change == 'app': body['appUserId'] = config['agents']['jarvis']['app_user_id']
    elif change == 'session_app': body['agentSession']['appUserId'] = config['agents']['jarvis']['app_user_id']
    elif change == 'session_org': body['agentSession']['organizationId'] = ident(90)
    elif change == 'issue': body['agentSession']['issueId'] = ident(90)
    elif change == 'stale': body['webhookTimestamp'] -= 61000
    elif change == 'future': body['webhookTimestamp'] += 61000
    elif change == 'action': body['action'] = 'deleted'
    elif change == 'event_type': body['type'] = 'Comment'
    raw, headers = signed(config, body)
    if change == 'signature': headers['Linear-Signature'] = '0' * 64
    with pytest.raises(ValueError): inbox.receive('codex', raw, headers, now=NOW)
    assert inbox.messages('codex') == []


def test_reused_delivery_or_source_cannot_change_contents(inbox, config):
    receive(inbox, config)
    altered = event(config); altered['promptContext'] = 'Different work'
    for delivery in [100, 101]:
        with pytest.raises(ValueError): receive(inbox, config, altered, delivery=delivery)
    assert len(inbox.messages('codex')) == 1


@pytest.mark.parametrize('author', [1, 2])
def test_agent_prompt_echo_does_not_trigger_agent(inbox, config, author):
    receive(inbox, config)
    body = event(config, action='prompted'); body['agentActivity']['userId'] = ident(author)
    with pytest.raises(ValueError): receive(inbox, config, body, delivery=101)
    assert len(inbox.messages('codex')) == 1


def test_out_of_order_prompt_is_retained_by_sender_for_reconciliation(inbox, config):
    with pytest.raises(ValueError): receive(inbox, config, event(config, action='prompted'))
    assert inbox.messages('codex') == []


def test_runtime_rebind_and_cross_agent_reply_refused(inbox, config):
    receive(inbox, config)
    with pytest.raises(ValueError): inbox.activity('codex', ident(7), 'result', 'response', 'Not bound')
    inbox.bind_runtime('codex', ident(7), 'native-1')
    with pytest.raises(ValueError): inbox.bind_runtime('codex', ident(7), 'native-2')
    with pytest.raises(ValueError): inbox.bind_runtime('jarvis', ident(7), 'native-1')
    with pytest.raises(ValueError): inbox.activity('jarvis', ident(7), 'result', 'response', 'Wrong app')


def test_activity_is_frozen_with_uuid_v4_for_uncertain_publication(inbox, config):
    receive(inbox, config); inbox.bind_runtime('codex', ident(7), 'native-1')
    first = inbox.activity('codex', ident(7), 'result', 'response', 'Synthetic result')
    assert uuid.UUID(first['variables']['input']['id']).version == 4
    assert inbox.activity('codex', ident(7), 'result', 'response', 'Synthetic result') == first
    with pytest.raises(ValueError): inbox.activity('codex', ident(7), 'result', 'response', 'Changed result')
    with pytest.raises(ValueError): inbox.activity('codex', ident(7), 'new', 'prompt', 'Impersonate human')


def test_store_policy_custody_and_immutable_evidence(inbox, config):
    receive(inbox, config)
    assert inbox.path.stat().st_mode & 0o777 == 0o600
    with sqlite3.connect(inbox.path) as db:
        with pytest.raises(sqlite3.IntegrityError): db.execute('DELETE FROM messages')
    changed = copy.deepcopy(config); changed['issues'][ident(6)]['plan_id'] = 'Other'
    with pytest.raises(ValueError): m.Inbox(inbox.root, changed)


@pytest.mark.parametrize('field', ['app_user_id', 'oauth_client_id', 'webhook_secret_file', 'access_token_file'])
def test_shared_agent_identity_or_credential_reference_refused(config, field):
    config['agents']['jarvis'][field] = config['agents']['codex'][field]
    with pytest.raises(ValueError): m.policy(config)


def test_secret_permissions_symlink_and_json_duplicate_checks(inbox, config, tmp_path):
    path = Path(config['agents']['codex']['webhook_secret_file']); path.chmod(0o644)
    with pytest.raises(ValueError): receive(inbox, config)
    link = tmp_path / 'secret-link'; link.symlink_to(path)
    with pytest.raises(ValueError): m.private_file(link)
    with pytest.raises(ValueError): m.decode(b'{"a":1,"a":2}')


@pytest.mark.parametrize('origin', ['http://example.com', 'https://localhost', 'https://127.0.0.1', 'https://a.example/path',
    'https://a.example/?token=x', 'https://user:secret@a.example', 'https://a.example:8443', 'https://a.local'])
def test_setup_refuses_nonpublic_or_credential_origins(origin):
    with pytest.raises(ValueError): setup.setup(origin)


def test_setup_has_two_independent_agents_and_no_installation():
    result = setup.setup('https://agents.example.com')
    assert result['configuration_changed'] is False and result['paid_model_calls'] == 0
    assert result['agents']['jarvis']['name'] == 'Jarvis' and result['agents']['codex']['name'] == 'Codex'
    assert result['agents']['jarvis']['webhook_url'] != result['agents']['codex']['webhook_url']
    assert result['agents']['codex']['manifest']['distribution'] == 'private'
    assert 'app:mentionable' in result['agents']['codex']['requested_scopes']


def http_call(inbox, path, raw, headers, method='POST'):
    import asyncio
    import httpx
    app = module('linear_http').create_app(inbox)
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://synthetic.invalid') as client:
            return await client.request(method, path, content=raw, headers=headers)
    return asyncio.run(run())


def test_http_routes_signed_event_without_launch_or_private_read(inbox, config, monkeypatch):
    monkeypatch.setattr(m.time, 'time', lambda: NOW)
    body = event(config); raw, headers = signed(config, body); headers['Content-Type'] = 'application/json'
    response = http_call(inbox, '/webhooks/codex', raw, headers)
    assert response.status_code == 202 and response.json()['agent'] == 'codex'
    assert len(inbox.messages('codex')) == 1
    assert http_call(inbox, '/webhooks/codex', b'', {}, 'GET').status_code == 405
    assert http_call(inbox, '/api/history', b'', {}, 'GET').status_code == 404
    assert http_call(inbox, '/oauth/codex/callback', b'', {}, 'GET').status_code == 404


def test_http_failure_does_not_echo_payload_or_credentials(inbox, config):
    raw, headers = signed(config, event(config)); headers['Content-Type'] = 'application/json'
    headers['Linear-Signature'] = '0' * 64
    response = http_call(inbox, '/webhooks/codex', raw, headers)
    assert response.status_code == 403 and 'Synthetic' not in response.text
    assert inbox.messages('codex') == []


def test_http_bounded_content_and_duplicate_headers(inbox, config):
    raw, headers = signed(config, event(config))
    assert http_call(inbox, '/webhooks/codex', raw, headers).status_code == 415
    headers['Content-Type'] = 'application/json'; headers['Content-Length'] = str(m.MAX_BODY + 1)
    assert http_call(inbox, '/webhooks/codex', raw, headers).status_code == 413
    pairs = [('Content-Type', 'application/json'), ('Linear-Delivery', ident(100)), ('Linear-Delivery', ident(101)),
        ('Linear-Signature', '0' * 64)]
    assert http_call(inbox, '/webhooks/codex', raw, pairs).status_code == 403
    assert inbox.messages('codex') == []


def test_bidirectional_handoff_preserves_work_and_requires_real_recipient_session(inbox, config):
    receive(inbox, config, agent='jarvis')
    inbox.bind_runtime('jarvis', ident(7), 'hermes-native')
    first = inbox.handoff('jarvis', ident(7), 'codex', 'handoff-1', 'Implement agreed SHRR-03 with the retained architecture.')
    assert inbox.handoff('jarvis', ident(7), 'codex', 'handoff-1', first['summary']) == first
    assert inbox.handoffs('codex') == [first] and inbox.handoffs('jarvis') == []
    with pytest.raises(ValueError): inbox.handoff_state('codex', first['handoff_id'], ident(9), 'accepted')
    receive(inbox, config, event(config, session=9), delivery=101)
    inbox.bind_runtime('codex', ident(9), 'codex-native')
    with pytest.raises(ValueError): inbox.handoff_state('codex', first['handoff_id'], ident(9), 'completed')
    accepted = inbox.handoff_state('codex', first['handoff_id'], ident(9), 'accepted')
    assert accepted['state'] == 'accepted'
    completed = inbox.handoff_state('codex', first['handoff_id'], ident(9), 'completed')
    assert completed['work_outcome_inferred'] is False
    back = inbox.handoff('codex', ident(9), 'jarvis', 'context-request', 'Summarize broader operator context.')
    assert back['binding'] == first['binding'] and back['execution_authorized'] is False
    assert len(inbox.messages('codex')) == 1 and len(inbox.messages('jarvis')) == 1


def test_changed_or_self_handoff_refused(inbox, config):
    receive(inbox, config); inbox.bind_runtime('codex', ident(7), 'codex-native')
    with pytest.raises(ValueError): inbox.handoff('codex', ident(7), 'codex', 'self', 'Loop')
    inbox.handoff('codex', ident(7), 'jarvis', 'context', 'A context request')
    with pytest.raises(ValueError): inbox.handoff('codex', ident(7), 'jarvis', 'context', 'Changed work')


def test_explicit_publication_checks_actor_and_reuses_receipt(inbox, config):
    receive(inbox, config); inbox.bind_runtime('codex', ident(7), 'native-1')
    frozen = inbox.activity('codex', ident(7), 'reply', 'response', 'Synthetic response')
    publisher = module('linear_publication'); calls = []
    def call(request):
        calls.append(request)
        if request['query'].startswith('query'):
            return dict(viewer={'id': config['agents']['codex']['app_user_id']}, organization={'id': config['organization_id']})
        return {'agentActivityCreate': dict(success=True, agentActivity={'id': frozen['variables']['input']['id']})}
    first = publisher.publish(inbox, 'codex', 'reply', call)
    assert first['actor_id'] == config['agents']['codex']['app_user_id'] and len(calls) == 2
    assert publisher.publish(inbox, 'codex', 'reply', call) == first and len(calls) == 2


def test_other_agent_token_or_operator_token_cannot_publish_as_codex(inbox, config):
    receive(inbox, config); inbox.bind_runtime('codex', ident(7), 'native-1')
    inbox.activity('codex', ident(7), 'reply', 'response', 'Synthetic response')
    calls = []
    def call(request):
        calls.append(request)
        return dict(viewer={'id': config['agents']['jarvis']['app_user_id']}, organization={'id': config['organization_id']})
    with pytest.raises(ValueError): module('linear_publication').publish(inbox, 'codex', 'reply', call)
    assert len(calls) == 1 and inbox.publication('codex', 'reply')['state'] == 'ready'


def test_lost_mutation_response_does_not_send_second_activity(inbox, config):
    receive(inbox, config); inbox.bind_runtime('codex', ident(7), 'native-1')
    inbox.activity('codex', ident(7), 'reply', 'response', 'Synthetic response')
    calls = []
    def call(request):
        calls.append(request)
        if request['query'].startswith('query'):
            return dict(viewer={'id': config['agents']['codex']['app_user_id']}, organization={'id': config['organization_id']})
        raise ValueError('synthetic lost response after remote commit')
    publisher = module('linear_publication')
    with pytest.raises(ValueError): publisher.publish(inbox, 'codex', 'reply', call)
    with pytest.raises(ValueError): publisher.publish(inbox, 'codex', 'reply', call)
    assert len(calls) == 2 and inbox.publication('codex', 'reply')['state'] == 'uncertain'
