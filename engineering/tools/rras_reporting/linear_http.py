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


def create_app(inbox):
    limits = local('linear_agents')
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
    return Starlette(routes=[Route('/webhooks/{agent}', webhook, methods=['POST'])])
