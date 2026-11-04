"""Signed fixture identities and actual private store reads; no live Cloudflare."""
import asyncio
import copy
import importlib.util
import json
import os
from pathlib import Path
import time
import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from test_engineering_history_local import store,request,note,document,create,module

TOOLS=Path(__file__).resolve().parents[1]/'tools/rras_history_web'
def web(name):
    spec=importlib.util.spec_from_file_location('test_dashboard_'+name,TOOLS/(name+'.py'))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

auth=web('access');history=web('history');app_module=web('app')
ISSUER='https://fixture.cloudflareaccess.com';AUDIENCE='fixture-audience';EMAIL='owner@example.test';ORIGIN='https://history.example.test'

@pytest.fixture(scope='module')
def key():return rsa.generate_private_key(public_exponent=65537,key_size=2048)

def jwks(key,kid='key-1'):
    public=json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()));public.update(kid=kid,use='sig',alg='RS256')
    return {'keys':[public]}

def config():return auth.AccessConfig(ISSUER,AUDIENCE,EMAIL,ORIGIN)

def claims(**changes):
    now=int(time.time());value=dict(iss=ISSUER,aud=[AUDIENCE],email=EMAIL,sub='fixture-subject',iat=now-5,nbf=now-5,exp=now+300)
    value.update(changes);return value

def token(key,values=None,headers=None):return jwt.encode(values or claims(),key,algorithm='RS256',headers=headers or {'kid':'key-1'})

def headers(value):return [(b'host',b'history.example.test'),(b'cf-access-jwt-assertion',value.encode())]

def access(key):return auth.Access(config(),auth.Keys(config(),lambda:jwks(key)))


def test_real_signature_and_single_operator_required(key):
    assert access(key).verify(headers(token(key)))=={'email':EMAIL,'subject':'fixture-subject'}
    with pytest.raises(auth.Denied):access(key).verify(headers(token(key,claims(email='other@example.test'))))
    fake=[(b'host',b'history.example.test'),(b'cf-access-authenticated-user-email',EMAIL.encode())]
    with pytest.raises(auth.Denied):access(key).verify(fake)


@pytest.mark.parametrize('change',[
    {'iss':'https://other.cloudflareaccess.com'}, {'aud':['other']}, {'exp':1}, {'nbf':int(time.time())+3600},
    {'iat':int(time.time())+3600},{'email':None},{'sub':''},{'iat':False}])
def test_bad_signed_claims_refuse(key,change):
    with pytest.raises(auth.Denied):access(key).verify(headers(token(key,claims(**change))))


@pytest.mark.parametrize('field',['iss','aud','exp','iat','nbf','sub','email'])
def test_missing_required_claims_refuse(key,field):
    value=claims();value.pop(field)
    with pytest.raises(auth.Denied):access(key).verify(headers(token(key,value)))


def test_wrong_signature_hs256_and_unsigned_tokens_refuse(key):
    another=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    for encoded in (token(another),jwt.encode(claims(),'s'*64,algorithm='HS256',headers={'kid':'key-1'}),jwt.encode(claims(),None,algorithm='none',headers={'kid':'key-1'})):
        with pytest.raises(auth.Denied):access(key).verify(headers(encoded))


@pytest.mark.parametrize('extra',[{'jku':'https://attacker.test/keys'},{'x5u':'https://attacker.test/cert'},{'jwk':{}},{'crit':['custom']}])
def test_token_cannot_select_key_source(key,extra):
    with pytest.raises(auth.Denied):access(key).verify(headers(token(key,headers={'kid':'key-1',**extra})))


@pytest.mark.parametrize('change',['duplicate_token','wrong_host','duplicate_host','foreign_origin','duplicate_origin','large_token'])
def test_origin_and_header_bounds(key,change):
    value=headers(token(key))
    if change=='duplicate_token':value.append(value[-1])
    if change=='wrong_host':value[0]=(b'host',b'other.example.test')
    if change=='duplicate_host':value.append(value[0])
    if change=='foreign_origin':value.append((b'origin',b'https://attacker.test'))
    if change=='duplicate_origin':value.extend([(b'origin',ORIGIN.encode())]*2)
    if change=='large_token':value[-1]=(b'cf-access-jwt-assertion',b'a'*16385)
    with pytest.raises(auth.Denied):access(key).verify(value)


def test_duplicate_signed_json_claims_refuse_before_key_fetch(key):
    head=jwt.utils.base64url_encode(b'{"alg":"RS256","kid":"key-1"}')
    body=jwt.utils.base64url_encode(b'{"email":"owner@example.test","email":"other@example.test"}')
    signature=jwt.algorithms.RSAAlgorithm(jwt.algorithms.RSAAlgorithm.SHA256).sign(head+b'.'+body,key)
    encoded=(head+b'.'+body+b'.'+jwt.utils.base64url_encode(signature)).decode()
    a=auth.Access(config(),auth.Keys(config(),lambda:pytest.fail('duplicate claims cannot fetch keys')))
    with pytest.raises(auth.Denied):a.verify(headers(encoded))


def test_key_cache_rotation_rate_limit_and_expiry(key):
    now=[0];calls=[];current=[jwks(key)]
    def loader():calls.append(1);return current[0]
    keys=auth.Keys(config(),loader,lambda:now[0]);keys.get('key-1');keys.get('key-1');assert len(calls)==1
    with pytest.raises(auth.Denied):keys.get('unknown')
    assert len(calls)==1
    now[0]=31;current[0]=jwks(key,'key-2');keys.get('key-2');assert len(calls)==2
    with pytest.raises(auth.Denied):keys.get('key-1')
    now[0]=400
    def unavailable():raise OSError('private detail')
    keys.loader=unavailable
    with pytest.raises(auth.Denied):keys.get('key-2')
    assert keys.url==ISSUER+'/cdn-cgi/access/certs'


@pytest.mark.parametrize('mutation',['empty','duplicate','private','hs256','small'])
def test_unusable_key_sets_refuse(key,mutation):
    value=jwks(key)
    if mutation=='empty':value['keys']=[]
    if mutation=='duplicate':value['keys']*=2
    if mutation=='private':value['keys'][0]['d']='secret'
    if mutation=='hs256':value['keys'][0]['alg']='HS256'
    if mutation=='small':value=jwks(rsa.generate_private_key(public_exponent=65537,key_size=1024))
    with pytest.raises(auth.Denied):auth.Keys(config(),lambda:value).get('key-1')


@pytest.fixture
def reader(store):
    create(store);head=store.history()['records'][0]['receipt']['work_revision_sha256']
    store.submit(note(head));store.submit(document(head))
    boundary=module('access').Access(store,{'contract':'engineering-history-access.v1','principals':[{'uid':os.getuid(),'private_read':['example'],'write':[]}]})
    calls=[]
    def call(message):calls.append(copy.deepcopy(message));return boundary.dispatch(os.getuid(),message)
    value=history.Reader(['example'],call);value.calls=calls;value.store=store;return value


def test_reader_uses_only_history_and_exact_scoped_document(reader):
    works=reader.works('example');assert works['total']==1 and works['works'][0]['records']==3
    work_id=works['works'][0]['work_item_id'];detail=reader.work('example',work_id)
    assert detail['release_status']=='not_inferred' and detail['timeline'][0]['occurred_at'] is None
    doc=detail['documents'][0];value=reader.document('example',work_id,doc['document_id'],doc['version'])
    assert value['digest_verified'] is True
    assert set(m['method'] for m in reader.calls)=={'history','document'}


def test_outcome_is_reported_not_inferred_and_revision_order_correct(reader):
    first=reader.store.history()['records'][0]['submission'];head=module('contract').digest(module('contract').encoded(first['body']))
    reader.store.submit(request('outcome.record','reported',head,dict(work_item_id=first['body']['work_item_id'],work_revision_sha256=head,outcome='completed_claim',summary='Reported only',references=[])))
    work=reader.works('example')['works'][0];assert work['latest_outcome']=='completed_claim' and work['records']==4


def test_unauthorized_repository_denied_without_any_service_call(reader):
    with pytest.raises(ValueError):reader.works('other')
    assert reader.calls==[]


@pytest.mark.parametrize('change',['work','version','document'])
def test_document_cannot_escape_selected_work(reader,change):
    work=reader.works('example')['works'][0]['work_item_id'];doc=reader.work('example',work)['documents'][0]
    before=len([c for c in reader.calls if c['method']=='document'])
    with pytest.raises(ValueError):reader.document('example','wrk_'+'f'*32 if change=='work' else work,'doc_'+'f'*32 if change=='document' else doc['document_id'],2 if change=='version' else 1)
    assert len([c for c in reader.calls if c['method']=='document'])==before


@pytest.mark.parametrize('change',['markdown','manifest'])
def test_document_digest_tamper_refuses(reader,change):
    original=reader.call
    def changed(message):
        value=original(message)
        if message['method']=='document':
            if change=='markdown':value['markdown']+='<script>private</script>'
            else:value['manifest']['status']='changed'
        return value
    reader.call=changed;work=reader.works('example')['works'][0]['work_item_id'];doc=reader.work('example',work)['documents'][0]
    with pytest.raises(ValueError):reader.document('example',work,doc['document_id'],1)


@pytest.mark.parametrize('change',['cursor','authority','receipt','wrong_repo','oversized_page'])
def test_malformed_service_data_refuses(reader,change):
    original=reader.call
    def changed(message):
        value=copy.deepcopy(original(message))
        if change=='cursor':value['next_offset']+=1
        if change=='authority':value['authority_granted']=True
        if change=='receipt':value['records'][0]['receipt']['request_sha256']='0'*64
        if change=='wrong_repo':value['records'][0]['submission']['body']['repository_id']='other'
        if change=='oversized_page':value['records']*=10
        return value
    reader.call=changed
    with pytest.raises(ValueError):reader.works('example')


def test_evidence_links_are_not_arbitrary_fetch_or_script():
    body={'references':[{'id':'javascript:alert(1)'},{'id':'https://github.com.evil.test/repo'},{'id':'https://user:secret@github.com/repo'},{'id':'https://github.com/owner/repo/pull/1'},{'id':'https://[bad'}]}
    assert history.evidence(body)==[{'url':'https://github.com/owner/repo/pull/1','label':'github.com/owner/repo/pull/1'}]


def client_call(app,key,path='/',method='GET',extra=None):
    async def go():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url=ORIGIN) as client:
            kwargs={'headers':{'Cf-Access-Jwt-Assertion':token(key),**(extra or {})}}
            return await client.request(method,path,**kwargs)
    return asyncio.run(asyncio.wait_for(go(),10))


def test_app_requires_auth_before_private_reads(reader,key):
    app=app_module.create_app(reader,access(key))
    async def go():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url=ORIGIN) as client:
            return await client.get('/api/works?repository_id=example')
    result=asyncio.run(asyncio.wait_for(go(),10));assert result.status_code==403 and reader.calls==[]
    assert 'Bounded fixture' not in result.text and result.headers['cache-control']=='no-store, private'


def test_authenticated_ui_and_exact_document_api(reader,key):
    app=app_module.create_app(reader,access(key));assert client_call(app,key).status_code==200
    works=client_call(app,key,'/api/works?repository_id=example').json();assert works['total']==1
    work_id=works['works'][0]['work_item_id'];detail=client_call(app,key,'/api/works/'+work_id+'?repository_id=example').json()
    doc=detail['documents'][0]
    result=client_call(app,key,'/api/documents/'+doc['document_id']+'?repository_id=example&work_id='+work_id+'&version=1')
    assert result.status_code==200 and result.json()['digest_verified'] is True
    assert 'frame-ancestors' in result.headers['content-security-policy'] and 'access-control-allow-origin' not in result.headers


@pytest.mark.parametrize('method',['POST','PUT','PATCH','DELETE','OPTIONS'])
def test_mutation_and_action_routes_never_dispatch(reader,key,method):
    app=app_module.create_app(reader,access(key));result=client_call(app,key,'/api/submit',method)
    assert result.status_code==405 and reader.calls==[]


@pytest.mark.parametrize('path',['/api/works?repository_id=example&repository_id=other','/api/works?repository_id=example&limit=true','/api/works?repository_id=example&unexpected=1'])
def test_invalid_queries_refuse_before_service(reader,key,path):
    app=app_module.create_app(reader,access(key));assert client_call(app,key,path).status_code==400
    assert reader.calls==[]


def test_revoked_or_unavailable_service_has_no_stale_fallback_or_private_errors(reader,key):
    app=app_module.create_app(reader,access(key));assert client_call(app,key,'/api/works?repository_id=example').status_code==200
    def revoked(_):raise OSError('SENTINEL private /path token')
    reader.call=revoked;result=client_call(app,key,'/api/works?repository_id=example')
    assert result.status_code==503 and 'SENTINEL' not in result.text and 'Bounded fixture' not in result.text


def test_assets_and_unknown_paths_cannot_read_arbitrary_files(reader,key):
    app=app_module.create_app(reader,access(key))
    assert client_call(app,key,'/assets/app.js').status_code==200
    assert client_call(app,key,'/assets/secrets').status_code==404
    assert client_call(app,key,'/api/execute').status_code==404
    assert reader.calls==[]
