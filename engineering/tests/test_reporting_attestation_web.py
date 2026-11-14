import asyncio
import importlib.util
from pathlib import Path
import httpx
from test_history_web import key,access,headers,token,ORIGIN
from test_reporting_onboarding_drafts import setup_draft,store,projects,uid
from test_reporting_human_attestation_store import fixture,STATEMENT

path=Path(__file__).resolve().parents[1]/'tools/rras_reporting/onboarding_attestation_web.py'
spec=importlib.util.spec_from_file_location('attestation_web_fixture',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_authenticated_attestation_browser_flow_and_origin_refusal(tmp_path,setup_draft,key):
    service,raw,review,source,tick=fixture(tmp_path,setup_draft,key)
    app=module.create_app(service,access(key))
    signed={k.decode():v.decode() for k,v in headers(token(key))}
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url=ORIGIN) as client:
            assert (await client.get('/')).status_code==403
            page=await client.get('/',headers=signed)
            assert page.status_code==200 and "frame-ancestors 'none'" in page.headers['content-security-policy']
            assert (await client.post('/api/attestation/begin',headers=signed,json={'review_id':uid(10),'comment_id':uid(8)})).status_code==403
            cross=dict(signed,origin='https://wrong.test')
            assert (await client.post('/api/attestation/begin',headers=cross,json={'review_id':uid(10),'comment_id':uid(8)})).status_code==403
            good=dict(signed,origin=ORIGIN)
            begin=await client.post('/api/attestation/begin',headers=good,json={'review_id':uid(10),'comment_id':uid(8)})
            assert begin.status_code==200 and begin.json()['source_text']==source['comment']['body']
            done=await client.post('/api/attestation/confirm',headers=good,json={'challenge':begin.json()['challenge'],'statement':STATEMENT})
            assert done.status_code==200 and done.json()['attested'] and not done.json()['execution_authorized']
            assert service.verify_authorship(source['comment'],review)
            again=await client.post('/api/attestation/confirm',headers=good,json={'challenge':begin.json()['challenge'],'statement':STATEMENT})
            assert again.status_code==403
    asyncio.run(run())


def test_browser_script_is_valid_javascript():
    import os,shutil,subprocess,pytest
    node=shutil.which('node')
    if not node and os.environ.get('SHRR_NODE_DOCKER')!='1':pytest.skip('Node required')
    command=[node,'--check'] if node else ['docker','exec','-i','n8n','node','--check']
    result=subprocess.run(command,input=module.JS,capture_output=True,timeout=15)
    assert result.returncode==0,result.stderr.decode()


def test_prefixed_browser_flow_preserves_authorization_and_routes(tmp_path,setup_draft,key):
    service,raw,review,source,tick=fixture(tmp_path,setup_draft,key)
    app=module.create_app(service,access(key),'/engineering-approval')
    signed={k.decode():v.decode() for k,v in headers(token(key))}
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url=ORIGIN) as client:
            path='/engineering-approval'
            assert (await client.get(path)).status_code==403
            page=await client.get(path,headers=signed)
            assert page.status_code==200 and '/engineering-approval/assets/attestation.js' in page.text
            script=await client.get(path+'/assets/attestation.js',headers=signed)
            assert path+'/api/attestation/begin' in script.text
            assert (await client.get('/',headers=signed)).status_code==404
            good=dict(signed,origin=ORIGIN)
            begin=await client.post(path+'/api/attestation/begin',headers=good,json={'review_id':uid(10),'comment_id':uid(8)})
            assert begin.status_code==200
            done=await client.post(path+'/api/attestation/confirm',headers=good,json={'challenge':begin.json()['challenge'],'statement':STATEMENT})
            assert done.status_code==200 and done.json()['attested'] and not done.json()['execution_authorized']
    asyncio.run(run())


def test_browser_refuses_ambiguous_path_prefixes():
    import pytest
    for prefix in ('/', '//other', '/bad/', '/bad/../x', '/CAPS', '/path?x=1', '/bad%2fpath', 1):
        with pytest.raises(ValueError):module.path_prefix(prefix)
