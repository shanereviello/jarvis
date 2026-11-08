"""Render private Linear registrations. v0.4 uses n8n OAuth and verified ingress.

Legacy standalone rendering is retained for old fixtures; CLI requires an explicit
legacy flag and must not be used for the approved n8n deployment.
"""
import argparse
import ipaddress
import json
from pathlib import Path
from urllib.parse import urlencode, urlsplit

NAMES = {'jarvis': ('Jarvis', 'Overall assistant and engineering-work coordinator, powered by Hermes.'),
         'codex': ('Codex', 'Coder and engineer; direct operator conversations and architecture decisions.')}


def setup(base, roles=('jarvis', 'codex')):
    if not roles or len(set(roles)) != len(roles) or not set(roles) <= set(NAMES):
        raise ValueError('explicit unique agent roles required')
    parsed = urlsplit(base)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.port or
            parsed.query or parsed.fragment or parsed.path not in ('', '/') or parsed.hostname != parsed.netloc or
            not all(part and part.replace('-', '').isalnum() for part in parsed.hostname.split('.')) or
            '.' not in parsed.hostname or parsed.hostname.endswith(('.localhost', '.local', '.invalid'))):
        raise ValueError('public HTTPS origin without path or credentials required')
    try:
        ipaddress.ip_address(parsed.hostname)
    except ValueError: pass
    else: raise ValueError('public DNS hostname required')
    base = 'https://' + parsed.hostname
    agents = {}
    for role, (name, description) in NAMES.items():
        if role not in roles: continue
        callback = base + '/oauth/' + role + '/callback'
        webhook = base + '/webhooks/' + role
        manifest = {'$schema': 'https://linear.app/.well-known/oauth-app-manifest.schema.json',
            'schemaVersion': '1.0.0', 'distribution': 'private', 'display': {'description': description},
            'developer': {'name': 'Reviello Robotics'},
            'oauth': {'client_name': name, 'client_uri': 'https://github.com/shanereviello/jarvis',
                      'redirect_uris': [callback], 'grant_types': ['authorization_code']},
            'webhook': {'enabled': True, 'url': webhook, 'resourceTypes': ['AgentSessionEvent']}}
        params = [('distribution', 'private'), ('display.description', description), ('developer.name', 'Reviello Robotics'),
            ('oauth.client_name', name), ('oauth.client_uri', manifest['oauth']['client_uri']),
            ('oauth.redirect_uris', callback), ('oauth.grant_types', 'authorization_code'),
            ('webhook.enabled', 'true'), ('webhook.url', webhook), ('webhook.resourceTypes', 'AgentSessionEvent')]
        agents[role] = dict(name=name, manifest=manifest,
            creation_url='https://linear.app/settings/api/applications/new?' + urlencode(params),
            requested_scopes=['read', 'write', 'app:mentionable', 'app:assignable'], actor='app',
            callback_url=callback, webhook_url=webhook, enabled_by_this_tool=False)
    return dict(contract='linear-agent-setup.v1', public_origin=base, agents=agents,
        required_before_installation=['Reviewed callback/event service deployed on this origin',
            'Workspace-admin registration and OAuth installation of selected apps; preserve existing integrations',
            'Distinct private client/token/webhook-secret files and pinned actor/workspace IDs',
            'Verified authorized Codex and Hermes message/session adapters'],
        paid_model_calls=0, configuration_changed=False)


def n8n_setup(callback, webhook):
    for value in (callback, webhook):
        if not isinstance(value, str): raise ValueError('both reviewed endpoints required')
        parsed = urlsplit(value)
        setup(parsed.scheme + '://' + parsed.netloc, ('codex',))
        if parsed.query or parsed.fragment or parsed.username or parsed.password:
            raise ValueError('credential-free exact registration endpoints required')
    if not urlsplit(callback).path.endswith('/oauth2-credential/callback'):
        raise ValueError('use the OAuth Redirect URL displayed by n8n')
    if urlsplit(webhook).path != '/webhooks/codex':
        raise ValueError('dedicated verified Codex webhook required')
    result = setup('https://' + urlsplit(webhook).netloc, ('codex',))
    agent = result['agents']['codex']
    agent['manifest']['oauth']['redirect_uris'] = [callback]
    agent['manifest']['webhook']['url'] = webhook
    agent.update(callback_url=callback, webhook_url=webhook)
    params = [('distribution', 'private'), ('oauth.client_name', 'Codex'),
        ('oauth.redirect_uris', callback), ('oauth.grant_types', 'authorization_code'),
        ('webhook.enabled', 'true'), ('webhook.url', webhook),
        ('webhook.resourceTypes', 'AgentSessionEvent')]
    agent['creation_url'] = 'https://linear.app/settings/api/applications/new?' + urlencode(params)
    result.update(contract='linear-agent-setup.v2', transport='existing-n8n', preserve_existing_jarvis=True,
        required_before_installation=['Reviewed verified Codex ingress and inactive n8n routes prepared',
            'Distinct n8n OAuth2 credential with actor=app and read write app:mentionable app:assignable',
            'Workspace-admin installation only after deployment decision; no Jarvis reauthorization',
            'Pin actual Codex actor, organization and issue/work/runtime authority before enabling dispatch'])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument('--public-origin')
    target.add_argument('--n8n-redirect-url')
    parser.add_argument('--verified-webhook-url')
    parser.add_argument('--legacy-standalone', action='store_true')
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--agent', choices=sorted(NAMES), action='append', help='Render only selected app(s); omit for both')
    args = parser.parse_args()
    if args.n8n_redirect_url:
        if args.legacy_standalone or args.agent not in (None, ['codex']):
            parser.error('v0.4 preserves Jarvis; render Codex only')
        result = n8n_setup(args.n8n_redirect_url, args.verified_webhook_url)
    else:
        if not args.legacy_standalone or args.verified_webhook_url:
            parser.error('standalone OAuth is superseded; use n8n endpoints')
        result = setup(args.public_origin, args.agent or ('jarvis', 'codex'))
    args.output.mkdir(mode=0o700, parents=False, exist_ok=False)
    for role, value in result['agents'].items():
        (args.output / (role + '-manifest.json')).write_text(json.dumps(value['manifest'], indent=2) + '\n')
    (args.output / 'setup.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__': main()
