"""Separate signed-event HTTP boundary. No dashboard write routes or model calls."""
import importlib.util
from pathlib import Path
import sqlite3
import asyncio
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse, Response
from starlette.routing import Route


def local(name):
    spec = importlib.util.spec_from_file_location('reporting_http_' + name, Path(__file__).with_name(name + '.py'))
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value); return value


def create_app(inbox=None, *, oauth_vaults=None):
    limits = local('linear_agents')
    oauth_vaults = oauth_vaults or {}
    if not set(oauth_vaults) <= limits.ROLE_NAMES: raise ValueError('unknown OAuth route')
    for role, vault in oauth_vaults.items():
        if vault.config['agent'] != role: raise ValueError('cross-agent OAuth route')

    async def callback(request):
        headers = {'cache-control': 'no-store', 'referrer-policy': 'no-referrer',
                   'content-security-policy': "default-src 'none'; frame-ancestors 'none'", 'x-content-type-options': 'nosniff'}
        vault = oauth_vaults.get(request.path_params['agent'])
        if vault is None: return Response('Unavailable.', status_code=404, headers=headers)
        try:
            if len(request.scope.get('query_string', b'')) > 8192:
                raise ValueError('bounded callback required')
            pairs = list(request.query_params.multi_items())
            if len(pairs) != len(dict(pairs)): raise ValueError('duplicate callback parameter')
            # Vault timeouts bound remote exchange and identity checks. Do not cancel
            # the worker midway and report failure while it is still saving custody.
            result = await run_in_threadpool(vault.callback, dict(pairs))
            return Response('App connection verified.' if result['phase'] == 'active' else 'Installation declined.',
                            headers=headers)
        except (ValueError, KeyError, TypeError, UnicodeError, RecursionError):
            return Response('Installation refused or pending reconciliation. Consult local app status.', status_code=403, headers=headers)
        except (OSError, sqlite3.Error, TimeoutError):
            return Response('Installation unavailable. Preserve the local installation state.', status_code=503, headers=headers)

    async def webhook(request):
        if request.path_params['agent'] not in limits.ROLE_NAMES:
            return Response('Unavailable.', status_code=404)
        try:
            if request.url.query or sum(len(k) + len(v) for k, v in request.scope['headers']) > 16384:
                raise ValueError('bounded headers required')
            # Reject duplicated signed/delivery/content-length headers before dict normalization.
            relevant = {'linear-signature', 'linear-delivery', 'content-length'}
            keys = [k.decode().lower() for k, _ in request.scope['headers'] if k.decode().lower() in relevant]
            if len(keys) != len(set(keys)): raise ValueError('duplicate transport header')
            if request.headers.get('content-type', '').split(';', 1)[0].strip() != 'application/json':
                return Response('JSON required.', status_code=415)
            length = request.headers.get('content-length')
            if length is not None and (not length.isdigit() or not 1 <= int(length) <= limits.MAX_BODY):
                return Response('Bounded body required.', status_code=413)
            data = bytearray()
            async with asyncio.timeout(4):
                async for part in request.stream():
                    if len(data) + len(part) > limits.MAX_BODY:
                        return Response('Bounded body required.', status_code=413)
                    data.extend(part)
                receipt = await run_in_threadpool(inbox.receive, request.path_params['agent'], bytes(data), dict(request.headers))
            return JSONResponse(receipt, status_code=202, headers={'cache-control': 'no-store'})
        except (ValueError, KeyError, TypeError, UnicodeError, RecursionError):
            return Response('Event refused.', status_code=403, headers={'cache-control': 'no-store'})
        except (OSError, sqlite3.Error, TimeoutError):
            return Response('Intake unavailable; retain delivery.', status_code=503, headers={'cache-control': 'no-store'})
    routes = []
    if inbox is not None: routes.append(Route('/webhooks/{agent}', webhook, methods=['POST']))
    if oauth_vaults: routes.append(Route('/oauth/{agent}/callback', callback, methods=['GET']))
    return Starlette(routes=routes)
