"""Model-free PKCE/identity/atomic refresh tests; no real tokens or HTTP traffic."""
import base64
import copy
import hashlib
import hmac
import importlib.util
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
import uuid

import pytest

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location('oauth_test_' + name, ROOT / 'tools/rras_reporting' / (name + '.py'))
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value); return value


m = module('linear_oauth')
NOW = 1794067200
def ident(n): return str(uuid.UUID(int=n))


@pytest.fixture
def selected():
    return dict(contract='linear-agent-oauth.v1', agent='codex', organization_id=ident(1), oauth_client_id=ident(2),
                public_origin='https://agents.example.com', expected_actor_id=None, excluded_actor_ids=[ident(4), ident(5)])


class Provider:
    def __init__(self):
        self.calls, self.identities = [], []
        self.fail, self.fail_identity = None, False
        self.org, self.actor, self.app, self.active = ident(1), ident(3), True, True
        self.response = dict(access_token='synthetic-access-1', refresh_token='synthetic-refresh-1',
                             token_type='Bearer', expires_in=3600, scope='read write app:mentionable app:assignable')

    def endpoint(self, op, form):
        self.calls.append((op, copy.deepcopy(form)))
        if self.fail: raise self.fail('synthetic secret must never appear in a transport error')
        return copy.deepcopy(self.response) if op == 'token' else {}

    def identity(self, token):
        self.identities.append(token)
        if self.fail_identity: raise ValueError('fixture identity outage')
        return dict(viewer=dict(id=self.actor, app=self.app, active=self.active, name='Codex'), organization=dict(id=self.org))


@pytest.fixture
def provider(): return Provider()


@pytest.fixture
def vault(tmp_path, selected, provider):
    return m.Vault(tmp_path / 'codex', selected, create=True, endpoint=provider.endpoint, identity=provider.identity)


def start(vault):
    value = vault.begin(now=NOW)
    query = {k: v[0] for k, v in parse_qs(urlsplit(value['authorization_url']).query).items()}
    return query


def install(vault):
    query = start(vault)
    result = vault.callback(dict(state=query['state'], code='synthetic-code'), now=NOW + 1)
    return query, result


def test_pkce_app_flow_has_no_client_secret_or_jarvis_rotation_flag(vault, provider):
    query, result = install(vault)
    assert query['actor'] == 'app' and query['code_challenge_method'] == 'S256'
    assert 'update_scopes_on_existing_token' not in query
    form = provider.calls[0][1]
    assert form['grant_type'] == 'authorization_code' and form['client_id'] == ident(2)
    expected = base64.urlsafe_b64encode(hashlib.sha256(form['code_verifier'].encode()).digest()).rstrip(b'=').decode()
    assert expected == query['code_challenge'] and 'client_secret' not in form
    assert result['app_user_id'] == ident(3) and result['phase'] == 'active'
    assert result['execution_enabled'] is False
    assert 'synthetic-access' not in json.dumps(result)
    assert vault.access(ident(3), now=NOW + 2) == ('synthetic-access-1', 1)


def test_private_custody_and_frozen_configuration_survive_reopen(vault, selected, provider):
    install(vault)
    assert vault.root.stat().st_mode & 0o777 == 0o700
    assert vault.path.stat().st_mode & 0o777 == 0o600
    reopened = m.Vault(vault.root, selected, endpoint=provider.endpoint, identity=provider.identity)
    assert reopened.status() == vault.status()
    selected['oauth_client_id'] = ident(9)
    with pytest.raises(ValueError): m.Vault(vault.root, selected)


@pytest.mark.parametrize('change', ['wrong_state', 'expired', 'missing_state', 'extra', 'conflicting', 'unknown_actor_role'])
def test_callback_refused_before_any_remote_exchange(vault, provider, change):
    query = start(vault); params = dict(state=query['state'], code='synthetic-code'); now = NOW + 1
    if change == 'wrong_state': params['state'] = 'wrong-state'
    elif change == 'expired': now = NOW + 601
    elif change == 'missing_state': del params['state']
    elif change == 'extra': params['redirect_uri'] = 'https://attacker.example'
    elif change == 'conflicting': params['error'] = 'access_denied'
    else: params['error_description'] = 'conflicting outcome'
    with pytest.raises(ValueError): vault.callback(params, now=now)
    assert not provider.calls


def test_exact_callback_replay_has_no_second_exchange_and_changed_code_refused(vault, provider):
    query, result = install(vault)
    assert vault.callback(dict(state=query['state'], code='synthetic-code'), now=NOW + 900) == result
    with pytest.raises(ValueError): vault.callback(dict(state=query['state'], code='different-code'), now=NOW + 2)
    assert len(provider.calls) == 1
    with pytest.raises(ValueError): vault.begin(now=NOW + 900)


def test_denied_callback_consumes_state_and_can_start_an_explicit_new_install(vault, provider):
    query = start(vault)
    result = vault.callback(dict(state=query['state'], error='access_denied', error_description='private provider text'), now=NOW)
    assert result['phase'] == 'denied' and not provider.calls
    assert 'private provider text' not in vault.path.read_bytes().decode('latin1')
    new = vault.begin(now=NOW + 1)
    assert query['state'] not in new['authorization_url']


@pytest.mark.parametrize('change', ['wrong_org', 'human', 'jarvis', 'inactive', 'expected_actor', 'unexpected_scope', 'no_refresh'])
def test_tokens_quarantined_until_correct_workspace_app_and_scopes_verified(vault, provider, selected, tmp_path, change):
    if change == 'wrong_org': provider.org = ident(99)
    elif change == 'human': provider.app = False
    elif change == 'jarvis': provider.actor = ident(4)
    elif change == 'inactive': provider.active = False
    elif change == 'expected_actor':
        selected['expected_actor_id'] = ident(9)
        vault = m.Vault(tmp_path / 'pinned', selected, create=True, endpoint=provider.endpoint, identity=provider.identity)
    elif change == 'unexpected_scope': provider.response['scope'] += ' admin'
    else: provider.response.pop('refresh_token')
    query = start(vault)
    with pytest.raises(ValueError): vault.callback(dict(state=query['state'], code='synthetic-code'), now=NOW)
    assert vault.status()['phase'] == 'verifying'
    with pytest.raises(ValueError): vault.access(ident(3), now=NOW)
    # Credentials remain available for explicit revocation, never silently discarded.
    assert vault.revoke()['phase'] == 'revoked'
    assert provider.calls[-1][1] == dict(token='synthetic-access-1', token_type_hint='access_token')


def test_identity_outage_can_be_reconciled_without_reexchanging_code_or_extending_expiry(vault, provider):
    query = start(vault); provider.fail_identity = True
    with pytest.raises(ValueError): vault.callback(dict(state=query['state'], code='synthetic-code'), now=NOW)
    provider.fail_identity = False
    result = vault.reconcile_identity(now=NOW + 1000)
    assert result['expires_at'] == NOW + 3600 and len(provider.calls) == 1


def test_lost_exchange_response_never_automatically_replays_code(vault, provider, selected):
    query = start(vault); provider.fail = TimeoutError
    with pytest.raises(TimeoutError): vault.callback(dict(state=query['state'], code='synthetic-code'), now=NOW)
    assert vault.status()['phase'] == 'exchanging'
    reopened = m.Vault(vault.root, selected, endpoint=provider.endpoint, identity=provider.identity)
    with pytest.raises(ValueError): reopened.callback(dict(state=query['state'], code='synthetic-code'), now=NOW + 1)
    with pytest.raises(ValueError): reopened.begin(now=NOW + 700)
    assert len(provider.calls) == 1


def test_refresh_pair_is_atomic_and_old_refusal_cannot_block_new_generation(vault, provider):
    install(vault)
    provider.response.update(access_token='synthetic-access-2', refresh_token='synthetic-refresh-2')
    result = vault.refresh(now=NOW + 3500)
    assert result['generation'] == 2 and result['expires_at'] == NOW + 7100
    assert provider.calls[-1][1]['refresh_token'] == 'synthetic-refresh-1'
    assert vault.access(ident(3), now=NOW + 3501)[0] == 'synthetic-access-2'
    assert vault.invalidate(1)['phase'] == 'active'
    assert vault.invalidate(2)['phase'] == 'invalid'
    with pytest.raises(ValueError): vault.access(ident(3), now=NOW + 3502)


def test_lost_refresh_response_requires_explicit_bounded_recovery_using_same_token(vault, provider):
    install(vault); provider.fail = TimeoutError
    with pytest.raises(TimeoutError): vault.refresh(now=NOW + 100)
    assert vault.status()['phase'] == 'refreshing'
    with pytest.raises(ValueError): vault.access(ident(3), now=NOW + 101)
    with pytest.raises(ValueError): vault.refresh(now=NOW + 102)
    with pytest.raises(ValueError): vault.revoke()
    provider.fail = None
    provider.response.update(access_token='synthetic-access-2', refresh_token='synthetic-refresh-2')
    result = vault.refresh(recover=True, now=NOW + 103)
    assert result['phase'] == 'active' and provider.calls[-1][1] == provider.calls[-2][1]


def test_refresh_recovery_outside_provider_window_is_refused(vault, provider):
    install(vault); provider.fail = TimeoutError
    with pytest.raises(TimeoutError): vault.refresh(now=NOW + 10)
    with pytest.raises(ValueError): vault.refresh(recover=True, now=NOW + 10 + 29 * 60)
    assert len(provider.calls) == 2


def test_revoked_refresh_does_not_retry_or_reinstall(vault, provider):
    install(vault); provider.fail = m.TokenRefused
    with pytest.raises(m.TokenRefused): vault.refresh(now=NOW + 100)
    assert vault.status()['phase'] == 'invalid'
    with pytest.raises(ValueError): vault.refresh(now=NOW + 101)
    assert len(provider.calls) == 2


def test_unknown_revoke_response_keeps_credentials_but_stops_use(vault, provider):
    install(vault); provider.fail = TimeoutError
    with pytest.raises(TimeoutError): vault.revoke()
    assert vault.status()['phase'] == 'revoking'
    with pytest.raises(ValueError): vault.access(ident(3), now=NOW + 2)
    provider.fail = None
    assert vault.revoke()['phase'] == 'revoked'
    assert vault.revoke()['phase'] == 'revoked'
    assert len(provider.calls) == 3


def test_private_root_permissions_and_symlink_database_refused(vault):
    vault.root.chmod(0o755)
    with pytest.raises(ValueError): vault.status()
    vault.root.chmod(0o700)
    moved = vault.path.with_suffix('.saved'); vault.path.rename(moved); vault.path.symlink_to(moved)
    with pytest.raises(ValueError): vault.status()


def test_codex_vault_does_not_need_any_jarvis_files(tmp_path, selected, provider):
    jarvis = tmp_path / 'jarvis-unavailable'; jarvis.mkdir(); jarvis.chmod(0)
    try:
        vault = m.Vault(tmp_path / 'codex-only', selected, create=True, endpoint=provider.endpoint, identity=provider.identity)
        install(vault)
        assert vault.access(ident(3), now=NOW + 2)[0] == 'synthetic-access-1'
    finally: jarvis.chmod(0o700)


def test_overlapping_callback_cannot_exchange_twice(vault, provider, selected):
    query = start(vault)
    entered, release = threading.Event(), threading.Event()
    def endpoint(op, form):
        entered.set()
        assert release.wait(5)
        return provider.endpoint(op, form)
    vault.endpoint = endpoint
    second = m.Vault(vault.root, selected, endpoint=provider.endpoint, identity=provider.identity)
    params = dict(state=query['state'], code='synthetic-code')
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(vault.callback, params, now=NOW + 1)
        try:
            assert entered.wait(5)
            with pytest.raises(BlockingIOError): second.callback(params, now=NOW + 1)
        finally: release.set()
        assert future.result()['phase'] == 'active'
    assert len(provider.calls) == 1
    assert second.callback(params, now=NOW + 2)['phase'] == 'active'


def test_codex_only_setup_does_not_recreate_existing_jarvis():
    result = module('linear_setup').setup('https://agents.example.com', roles=['codex'])
    assert set(result['agents']) == {'codex'}


def test_cross_actor_and_expired_tokens_are_never_exposed_to_caller(vault):
    install(vault)
    with pytest.raises(ValueError): vault.access(ident(4), now=NOW + 2)
    with pytest.raises(ValueError): vault.access(ident(3), now=NOW + 3541)


def test_scoped_publisher_blocks_401_without_retry_or_credential_export(vault, provider, monkeypatch):
    install(vault); monkeypatch.setattr(m.time, 'time', lambda: NOW + 2)
    calls = []
    def factory(token):
        assert token == 'synthetic-access-1'
        def call(request):
            calls.append(request)
            raise m.publication.AuthenticationRefused('fixture auth refusal')
        return call
    client = m.ScopedClient(vault, ident(3), client_factory=factory)
    with pytest.raises(ValueError): client({'query': 'query fixture'})
    with pytest.raises(ValueError): client({'query': 'query fixture'})
    assert len(calls) == 1 and vault.status()['phase'] == 'invalid'


def test_callback_http_is_bounded_replay_safe_and_does_not_echo_secrets(vault, provider):
    from starlette.testclient import TestClient
    query = start(vault)
    app = module('linear_http').create_app(oauth_vaults={'codex': vault})
    # Let the real callback clock agree with synthetic state without altering HTTP code.
    original = vault.callback
    vault.callback = lambda params: original(params, now=NOW + 1)
    with TestClient(app) as client:
        params = dict(state=query['state'], code='synthetic-code')
        result = client.get('/oauth/codex/callback', params=params)
        assert result.status_code == 200 and result.text == 'App connection verified.'
        assert result.headers['cache-control'] == 'no-store' and result.headers['referrer-policy'] == 'no-referrer'
        assert client.get('/oauth/codex/callback', params=params).status_code == 200
        assert len(provider.calls) == 1
        assert client.get('/oauth/jarvis/callback', params=params).status_code == 404
        assert client.get('/oauth/codex/callback?state=x&state=y&code=z').status_code == 403
        assert client.get('/oauth/codex/callback?state=' + 'a' * 8193).status_code == 403
        assert client.post('/oauth/codex/callback', json=params).status_code == 405
        assert client.get('/oauth/codex/begin').status_code == 404
        assert client.post('/webhooks/codex', json={}).status_code == 404


def test_cli_begin_saves_authorization_url_in_private_file_and_prints_only_path(tmp_path, selected, capsys):
    config = tmp_path / 'config.json'; config.write_text(json.dumps(selected)); config.chmod(0o600)
    state = tmp_path / 'vault'; output = tmp_path / 'authorization.json'
    entry = module('linear_oauth_entry')
    entry.main(['init', '--configuration', str(config), '--state', str(state)])
    capsys.readouterr()
    entry.main(['begin', '--configuration', str(config), '--state', str(state), '--authorization-file', str(output)])
    shown = capsys.readouterr().out
    assert 'authorization_url' not in shown and 'code_challenge' not in shown
    assert output.stat().st_mode & 0o777 == 0o600 and 'authorization_url' in json.loads(output.read_bytes())
    with pytest.raises(SystemExit):
        entry.main(['begin', '--configuration', str(config), '--state', str(state), '--authorization-file', str(output)])
    assert 'state=' not in capsys.readouterr().err


def test_explicit_cli_publisher_uses_verified_custody_and_replays_receipt_without_resending(
        tmp_path, vault, selected, monkeypatch, capsys):
    install(vault); monkeypatch.setattr(m.time, 'time', lambda: NOW + 2)
    core = module('linear_agents')
    agents = {}
    for role, actor, client in [('jarvis', ident(4), ident(9)), ('codex', ident(3), ident(2))]:
        secret = tmp_path / (role + '-webhook'); secret.write_bytes(b'synthetic-webhook-secret-at-least-24'); secret.chmod(0o600)
        agents[role] = dict(app_user_id=actor, oauth_client_id=client, webhook_secret_file=str(secret),
                            access_token_file=str(tmp_path / (role + '-unused-token')))
    policy = dict(contract='linear-agent-policy.v1', organization_id=ident(1), agents=agents,
        issues={ident(6): dict(project_id='prj_' + '1' * 32, work_id='wrk_' + '2' * 32,
            work_revision_sha256='3' * 64, architecture_version=3, architecture_sha256='4' * 64, plan_id='SHRR-03')})
    inbox = core.Inbox(tmp_path / 'inbox', policy, create=True)
    event = dict(type='AgentSessionEvent', action='created', appUserId=ident(3), oauthClientId=ident(2),
        organizationId=ident(1), webhookTimestamp=NOW * 1000, promptContext='Synthetic addressed request',
        agentSession=dict(id=ident(7), appUserId=ident(3), organizationId=ident(1), issueId=ident(6), creatorId=ident(5)))
    raw = core.encoded(event)
    inbox.receive('codex', raw, {'Linear-Signature': hmac.new(b'synthetic-webhook-secret-at-least-24', raw, hashlib.sha256).hexdigest(),
                                'Linear-Delivery': ident(30)}, now=NOW)
    inbox.bind_runtime('codex', ident(7), 'synthetic-native-session')
    inbox.activity('codex', ident(7), 'fixture-response', 'response', 'Synthetic engineer reply')
    policy_path, config_path = tmp_path / 'policy.json', tmp_path / 'oauth.json'
    for path, value in [(policy_path, policy), (config_path, selected)]:
        path.write_bytes(core.encoded(value)); path.chmod(0o600)
    calls = []
    def factory(token):
        assert token == 'synthetic-access-1'
        def call(request):
            calls.append(request)
            if 'variables' not in request: return dict(viewer=dict(id=ident(3)), organization=dict(id=ident(1)))
            return dict(agentActivityCreate=dict(success=True, agentActivity=dict(id=request['variables']['input']['id'])))
        return call
    monkeypatch.setattr(m.publication, 'Client', factory)
    entry = module('linear_agent_entry'); original = entry.local
    monkeypatch.setattr(entry, 'local', lambda name: m if name == 'linear_oauth' else original(name))
    args = ['publish', '--policy', str(policy_path), '--state', str(inbox.root), '--agent', 'codex',
            '--key', 'fixture-response', '--oauth-configuration', str(config_path), '--oauth-state', str(vault.root)]
    entry.main(args)
    result = json.loads(capsys.readouterr().out)
    assert result['actor_id'] == ident(3) and len(calls) == 2
    assert 'synthetic-access' not in json.dumps(result)
    entry.main(args)
    assert json.loads(capsys.readouterr().out) == result and len(calls) == 2
