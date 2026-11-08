"""Explicit one-activity publication. Frozen UUID, actor check, no automatic retry.

No invocation occurs from webhook intake. HTTP caller errors never include tokens
or provider response bodies. Existing authorizations still govern actual use.
"""
import json
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError


class AuthenticationRefused(ValueError): pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs): return None


class Client:
    def __init__(self, access_token):
        if type(access_token) is not str or not access_token or any(c.isspace() for c in access_token):
            raise ValueError('private app token required')
        self._token = access_token

    def __call__(self, request):
        raw = json.dumps(request, separators=(',', ':'), allow_nan=False).encode()
        if len(raw) > 128 * 1024: raise ValueError('bounded GraphQL request required')
        message = Request('https://api.linear.app/graphql', data=raw, method='POST', headers={
            'Content-Type': 'application/json', 'Authorization': 'Bearer ' + self._token})
        try:
            with build_opener(NoRedirect).open(message, timeout=5) as response:
                raw = response.read(1024 * 1024 + 1)
                if len(raw) > 1024 * 1024: raise ValueError('bounded response required')
                value = json.loads(raw)
                if type(value) is not dict or value.get('errors') or type(value.get('data')) is not dict:
                    raise ValueError('provider refused')
                return value['data']
        except HTTPError as error:
            if error.code == 401:
                raise AuthenticationRefused('Linear app authorization refused') from None
            raise ValueError('Linear unavailable or refused; preserve original activity and reconcile before retry') from None
        except Exception:
            raise ValueError('Linear unavailable or refused; preserve original activity and reconcile before retry') from None


def publish(inbox, agent, key, call):
    current = inbox.publication(agent, key)
    if current['state'] == 'recorded': return current['receipt']
    if current['state'] == 'uncertain': raise ValueError('publication uncertain; reconcile original ID')
    # The transport owns this app token; user/other-app tokens must fail before mutation.
    identity = call({'query': 'query ReportingIdentity { viewer { id } organization { id } }'})
    expected = inbox.policy['agents'][agent]['app_user_id']
    if identity.get('viewer', {}).get('id') != expected or identity.get('organization', {}).get('id') != inbox.policy['organization_id']:
        raise ValueError('publisher is not the selected app identity')
    started = inbox.publication(agent, key, begin=True)
    result = call(started['request'])
    created = result.get('agentActivityCreate', {})
    activity_id = started['request']['variables']['input']['id']
    if created.get('success') is not True or created.get('agentActivity', {}).get('id') != activity_id:
        raise ValueError('activity result uncertain; reconcile original ID')
    receipt = dict(agent=agent, key=key, activity_id=activity_id, actor_id=expected,
        organization_id=inbox.policy['organization_id'], publication='api_reported', execution_authorized=False)
    inbox.publication(agent, key, receipt=receipt)
    return receipt
