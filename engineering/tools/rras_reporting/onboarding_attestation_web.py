"""Inactive operator-only browser interface for ambiguous authorship.

The caller must supply the protected attestation store and the existing signed
Cloudflare Access verifier. This application neither installs a listener nor
records an architecture decision or enables execution by itself.
"""
import json
import re
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.responses import Response
from starlette.routing import Route


HEADERS={'cache-control':'no-store, private','pragma':'no-cache','x-content-type-options':'nosniff',
 'referrer-policy':'no-referrer','x-frame-options':'DENY','permissions-policy':'camera=(), microphone=(), geolocation=()',
 'content-security-policy':"default-src 'none'; script-src 'self'; connect-src 'self'; style-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
 'cross-origin-resource-policy':'same-origin'}
HTML=b'''<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Confirm architecture decision</title>
<meta name="viewport" content="width=device-width,initial-scale=1"></head><body>
<main><h1>Confirm architecture decision</h1><p>Confirm authorship only if you personally wrote the exact Linear approval shown below.</p>
<label>Review ID <input id="review" autocomplete="off"></label><br><label>Comment ID <input id="comment" autocomplete="off"></label>
<button id="load" type="button">Show decision</button><section id="details" hidden><h2>Decision</h2><pre id="record"></pre>
<p>I confirm I personally authored this exact Linear approval.</p><button id="confirm" type="button">Confirm authorship</button></section>
<p id="status" role="status"></p></main><script src="/assets/attestation.js" defer></script></body></html>'''
JS=b'''"use strict";let challenge=null;const byId=x=>document.getElementById(x);const status=byId("status");
const params=new URLSearchParams(location.search),uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
for(const [key,id] of [["review_id","review"],["comment_id","comment"]]){const values=params.getAll(key);if(values.length===1&&uuid.test(values[0]))byId(id).value=values[0]}
if(location.search)history.replaceState(null,"",location.pathname);
async function request(url,body){const r=await fetch(url,{method:"POST",credentials:"same-origin",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});if(!r.ok)throw Error("unavailable");return r.json()}
byId("load").addEventListener("click",async()=>{challenge=null;byId("details").hidden=true;status.textContent="Loading decision...";
 try{const value=await request("/api/attestation/begin",{review_id:byId("review").value.trim(),comment_id:byId("comment").value.trim()});
 challenge=value.challenge;byId("record").textContent="Project: "+value.linear_project_id+"\\nIssue: "+value.issue_id+"\\nArchitecture version: "+value.version+"\\nSHA-256: "+value.markdown_sha256+"\\nLinear approval:\\n"+value.source_text;byId("details").hidden=false;status.textContent=""}
 catch(_){status.textContent="Decision unavailable. Check the IDs and try again."}});
byId("confirm").addEventListener("click",async()=>{if(!challenge)return;const selected=challenge;challenge=null;byId("confirm").disabled=true;
 try{const result=await request("/api/attestation/confirm",{challenge:selected,statement:"I confirm I personally authored this exact Linear approval."});byId("details").hidden=true;status.textContent=result.decision_recorded===true?"Authorship confirmed and architecture decision recorded.":"Authorship confirmed. The architecture decision can now be recorded."}
 catch(_){status.textContent="Confirmation unavailable. Reload the decision before trying again."}finally{byId("confirm").disabled=false}});'''


def path_prefix(prefix):
    if type(prefix) is not str or len(prefix)>128 or (prefix and not re.fullmatch(r'/(?:[a-z0-9]+(?:-[a-z0-9]+)*)(?:/[a-z0-9]+(?:-[a-z0-9]+)*)*',prefix)):
        raise ValueError('canonical private application path required')
    return prefix


def create_app(store,access,prefix=''):
    prefix=path_prefix(prefix)
    html=HTML.replace(b'/assets/attestation.js',prefix.encode()+b'/assets/attestation.js')
    js=JS.replace(b'/api/attestation/',prefix.encode()+b'/api/attestation/')
    if not callable(getattr(access,'verify',None)) or not callable(getattr(store,'begin',None)) or not callable(getattr(store,'confirm',None)):
        raise ValueError('protected operator attestation service required')
    def response(value,status=200):
        return Response(json.dumps(value,ensure_ascii=True,separators=(',',':')).encode(),status_code=status,media_type='application/json',headers=HEADERS)
    async def validate(request,keys):
        if request.query_params or request.headers.get('content-type','').split(';')[0].strip().lower()!='application/json':raise ValueError()
        chunks=[];size=0
        async for chunk in request.stream():
            size+=len(chunk)
            if size>4096:raise ValueError()
            chunks.append(chunk)
        def pairs(items):
            value={}
            for k,v in items:
                if k in value:raise ValueError()
                value[k]=v
            return value
        value=json.loads(b''.join(chunks),object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(ValueError()))
        if type(value) is not dict or set(value)!=keys or any(type(x) is not str or len(x)>512 for x in value.values()):raise ValueError()
        return value
    async def index(_):return Response(html,media_type='text/html',headers=HEADERS)
    async def javascript(_):return Response(js,media_type='application/javascript',headers=HEADERS)
    async def begin(request):
        try:
            value=await validate(request,{'review_id','comment_id'})
            result=await run_in_threadpool(store.begin,request.scope['headers'],value['review_id'],value['comment_id'])
            return response(result)
        except Exception:return response({'error':'unavailable'},403)
    async def confirm(request):
        try:
            value=await validate(request,{'challenge','statement'})
            result=await run_in_threadpool(store.confirm,request.scope['headers'],value['challenge'],value['statement'])
            return response(result)
        except Exception:return response({'error':'unavailable'},403)
    app=Starlette(debug=False,routes=[Route(prefix or '/',index),Route(prefix+'/assets/attestation.js',javascript),
        Route(prefix+'/api/attestation/begin',begin,methods=['POST']),Route(prefix+'/api/attestation/confirm',confirm,methods=['POST'])])
    class Boundary:
        async def __call__(self,scope,receive,send):
            if scope['type']=='lifespan':return await app(scope,receive,send)
            if scope['type']!='http':return
            try:
                if len(scope.get('query_string',b''))>1024 or sum(len(k)+len(v) for k,v in scope.get('headers',[]))>32768:raise ValueError()
                await run_in_threadpool(access.verify,scope.get('headers',[]))
            except Exception:return await Response('Access unavailable.',status_code=403,headers=HEADERS)(scope,receive,send)
            return await app(scope,receive,send)
    return Boundary()
