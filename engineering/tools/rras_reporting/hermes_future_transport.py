"""Transport helpers for the future-session coordinator; no service is installed."""
import http.client
import importlib.util
import ipaddress
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit

IMAGE = 'sha256:b99f4564d5e17ec0183314c0d2f6f633657cff4916fad0f05f6e7667722da432'
ROUTE = '/webhook/rras-hermes-future-session-metadata'


def local(name):
    spec = importlib.util.spec_from_file_location('future_transport_' + name, Path(__file__).with_name(name + '.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def reader(url, token):
    parsed = urlsplit(url)
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except (ValueError, TypeError) as exc:
        raise ValueError('private registry address required') from exc
    if (parsed.scheme != 'http' or not (address == ipaddress.ip_address('127.0.0.1') or
                                        address in ipaddress.ip_network('172.19.0.0/16')) or
            parsed.port != 5678 or parsed.path != ROUTE or parsed.username or parsed.password or
            parsed.query or parsed.fragment or type(token) is not bytes or not 32 <= len(token) <= 256 or
            not all(33 <= value <= 126 for value in token)):
        raise ValueError('fixed private metadata reader required')
    def query(cursor):
        if type(cursor) is not dict or set(cursor) != {'after_time', 'after_id'}:
            raise ValueError('exact metadata cursor required')
        selector = local('hermes_capture_selection')
        selector.timestamp(cursor['after_time']); selector.identifier(cursor['after_id'])
        connection = http.client.HTTPConnection(str(address), 5678, timeout=20)
        try:
            connection.request('POST', ROUTE, body=json.dumps(cursor).encode(),
                headers={'Content-Type':'application/json', 'Authorization':'Bearer ' + token.decode()})
            response = connection.getresponse(); raw = response.read(65537)
            if response.status != 200 or len(raw) > 65536:
                raise ValueError('bounded metadata reader unavailable')
            return local('capture_intake').local('contract').decode(raw, max_bytes=65536)
        finally:
            connection.close()
    return query


def existing_hermes_worker(*, organization_id, cutoff, mappings, authorization_reference,
                           entry_source, container='hermes', execute=subprocess.run):
    """Invoke fixed reviewed source in Hermes; caller must pin container and source bytes."""
    selector = local('hermes_capture_selection')
    selector.identifier(organization_id); selector.timestamp(cutoff)
    if (type(entry_source) is not bytes or not 1 <= len(entry_source) <= 32768 or
            type(mappings) is not dict or type(authorization_reference) is not str or
            not 1 <= len(authorization_reference) <= 256 or
            not re.fullmatch(r'(?:hermes|rras-hermes-future-fixture-[0-9a-f]{12})', container)):
        raise ValueError('fixed selected native worker configuration required')
    selected_mappings = {}
    for issue, mapping in mappings.items():
        selector.identifier(issue)
        if type(mapping) is not dict:
            raise ValueError('fixed explicit issue scope required')
        effective_after = None
        if set(mapping) == {'scope', 'context', 'effective_after'}:
            scope, context = mapping['scope'], mapping['context']
            effective_after = selector.timestamp(mapping['effective_after'])
            if effective_after < selector.timestamp(cutoff):
                raise ValueError('mapping cannot predate the capture cutoff')
            if type(context) is not dict or type(context.get('work')) is not dict:
                raise ValueError('exact issue work context required')
            # Validate the same bounded context contract used by retained history.
            local('capture_intake').local('reporting_contract').validate(dict(
                contract='engineering-reporting.v1', operation='source.observe',
                client_event_key='future-context-validation', expected_head=None,
                scope=scope, context=context,
                source=dict(kind='imported', namespace='hermes_capture', id=None),
                occurred_at=None, body=dict(source=dict(namespace='hermes', id=issue),
                    source_observed_at=None, cursor=None, status='unknown', gaps=[],
                    detail='Validate explicit session-level work context.')))
        else:
            scope, context = mapping, None
        if (type(scope) is not dict or set(scope) != {'kind', 'id'} or
                scope['kind'] not in ('repository', 'non_git') or type(scope['id']) is not str or
                not re.fullmatch(r'[a-zA-Z0-9_-]{1,128}', scope['id']) or
                (scope['kind'] == 'non_git' and scope['id'] != 'jarvis-non-git')):
            raise ValueError('fixed explicit issue scope required')
        selected_mappings[issue] = (scope, context, effective_after)
    def invoke(request):
        if type(request) is not dict or set(request) != {'page', 'after_time', 'after_id'}:
            raise ValueError('bounded selected native page required')
        rows = selector.select_page(request['page'], organization_id=organization_id, cutoff=cutoff,
                                    after_time=request['after_time'], after_id=request['after_id'])
        output = []
        for row in rows:
            scope, context, effective_after = selected_mappings.get(row['issue_id'],
                (dict(kind='non_git', id='jarvis-non-git'), None, None))
            if effective_after is not None and selector.timestamp(row['created_at']) <= effective_after:
                context = None
            args = ['/usr/bin/docker', 'exec', '--user', '1000:1000', '-i', container, '/usr/bin/env', '-i',
                    'PATH=/usr/bin:/bin', 'HOME=/tmp', 'HERMES_HOME=/opt/data', 'LANG=C.UTF-8',
                    '/opt/hermes/.venv/bin/python', '-I', '-B', '-', organization_id,
                    row['agent_session_id'], scope['kind'], scope['id'], cutoff, authorization_reference]
            if context is not None:
                args.append(json.dumps(context, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False))
            result = execute(args, input=entry_source, capture_output=True, timeout=120)
            if result.returncode or len(result.stdout) > 4096:
                raise ValueError('selected Hermes export failed; retain source and queue')
            value = local('capture_intake').local('contract').decode(result.stdout, max_bytes=4096)
            if (type(value) is not dict or set(value) != {'session_id', 'changed', 'models_started'} or
                    value['session_id'] != row['agent_session_id'] or type(value['changed']) is not bool or
                    value['models_started'] != 0):
                raise ValueError('selected Hermes export result differs')
            output.append(dict(session_id=value['session_id'], changed=value['changed']))
        return dict(contract='hermes-future-capture-page.v1', sessions=output, models_started=0)
    return invoke
