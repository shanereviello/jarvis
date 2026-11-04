"""Source-only read-only dashboard; production packaging/entrypoint is separate."""
import json
from pathlib import Path
import re
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.responses import Response
from starlette.routing import Route


def response(value,status=200):
    raw=json.dumps(value,ensure_ascii=True,allow_nan=False,separators=(',',':')).encode()
    if len(raw)>2*1024*1024:return Response('History unavailable.',status_code=503,media_type='text/plain')
    return Response(raw,status_code=status,media_type='application/json')


HEADERS={
    'cache-control':'no-store, private','pragma':'no-cache','x-content-type-options':'nosniff',
    'referrer-policy':'no-referrer','x-frame-options':'DENY','permissions-policy':'camera=(), microphone=(), geolocation=()',
    'content-security-policy':"default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
    'cross-origin-resource-policy':'same-origin',
}


class Boundary:
    def __init__(self,app,access):self.app=app;self.access=access

    async def __call__(self,scope,receive,send):
        if scope['type']=='lifespan':return await self.app(scope,receive,send)
        if scope['type']!='http':
            if scope['type']=='websocket':await send({'type':'websocket.close','code':1008})
            return
        async def secured(message):
            if message['type']=='http.response.start':
                headers=[(k,v) for k,v in message.get('headers',[]) if k.decode().lower() not in HEADERS]
                message={**message,'headers':headers+[(k.encode(),v.encode()) for k,v in HEADERS.items()]}
            await send(message)
        try:
            if len(scope.get('query_string',b''))>4096 or sum(len(k)+len(v) for k,v in scope.get('headers',[]))>32768:raise ValueError()
            identity=await run_in_threadpool(self.access.verify,scope.get('headers',[]))
        except Exception:return await Response('Access unavailable.',status_code=403,media_type='text/plain')(scope,receive,secured)
        if scope['method'] not in ('GET','HEAD'):
            return await Response('Read-only application.',status_code=405,headers={'Allow':'GET, HEAD'})(scope,receive,secured)
        scope={**scope,'operator':identity}
        return await self.app(scope,receive,secured)


def create_app(reader,access):
    assets=Path(__file__).with_name('assets')
    payloads={name:(assets/name).read_bytes() for name in ('index.html','app.css','app.js')}
    def query(request,allowed):
        items=list(request.query_params.multi_items())
        if len({k for k,v in items})!=len(items) or any(k not in allowed for k,v in items):raise ValueError()
        return dict(items)
    def number(value,default):
        if value is None:return default
        if not re.fullmatch(r'[0-9]{1,8}',value):raise ValueError()
        return int(value)
    async def read(fn,*args):
        try:return response(await run_in_threadpool(fn,*args))
        except Exception:return Response('History unavailable. Refresh after access is restored.',status_code=503,media_type='text/plain')
    async def index(request):return Response(payloads['index.html'],media_type='text/html')
    async def asset(request):
        name=request.path_params['name']
        if name not in ('app.css','app.js'):return Response('Unavailable.',status_code=404)
        return Response(payloads[name],media_type='text/css' if name.endswith('.css') else 'application/javascript')
    async def repos(request):
        if request.query_params:return Response('Unavailable.',status_code=400)
        return response({'repositories':list(reader.repositories),'operator_email':request.scope['operator']['email'],'authority_granted':False})
    async def works(request):
        try:q=query(request,{'repository_id','q','offset','limit'});offset=number(q.get('offset'),0);limit=number(q.get('limit'),20)
        except ValueError:return Response('Unavailable.',status_code=400)
        return await read(reader.works,q.get('repository_id'),q.get('q',''),offset,limit)
    async def work(request):
        try:q=query(request,{'repository_id'})
        except ValueError:return Response('Unavailable.',status_code=400)
        return await read(reader.work,q.get('repository_id'),request.path_params['work_id'])
    async def document(request):
        try:q=query(request,{'repository_id','work_id','version'});version=number(q.get('version'),None)
        except ValueError:return Response('Unavailable.',status_code=400)
        return await read(reader.document,q.get('repository_id'),q.get('work_id'),request.path_params['document_id'],version)
    app=Starlette(debug=False,routes=[Route('/',index),Route('/assets/{name}',asset),Route('/api/repositories',repos),
        Route('/api/works',works),Route('/api/works/{work_id}',work),Route('/api/documents/{document_id}',document)])
    return Boundary(app,access)
