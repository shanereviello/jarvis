"""Isolated numeric-UID proof for a protected copy of the production package."""
import asyncio
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def run(root,evidence):
    root=Path(root);evidence=Path(evidence)
    if os.getuid()!=61164 or os.geteuid()!=61164 or os.getgid()!=61164 or os.getegid()!=61164 or os.getgroups():raise ValueError('fixed isolated probe identity required')
    status=dict(line.split(':',1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
    if status['NoNewPrivs'].strip()!='1' or any(int(status[k].strip(),16) for k in ('CapInh','CapPrm','CapEff','CapBnd','CapAmb')):raise ValueError('probe privileges retained')
    interfaces={line.split(':')[0].strip() for line in Path('/proc/net/dev').read_text().splitlines()[2:]}
    if interfaces!={'lo'} or len(Path('/proc/net/route').read_text().splitlines())!=1:raise ValueError('probe network not isolated')
    if set(os.environ)-{'PATH','HOME','LANG'}:raise ValueError('unexpected inherited environment')
    if not root.is_absolute() or root.resolve(strict=True)!=root:raise ValueError('protected copy required')
    for path in (root,*root.parents):
        info=path.lstat()
        if info.st_uid!=0 or info.st_mode&0o022:raise ValueError('unprotected runtime ancestor')
    for path in (root/'forbidden-write',root/'vendor/forbidden-write'):
        try:
            with path.open('xb'):pass
        except PermissionError:pass
        else:raise ValueError('protected payload writable')
    try:list(evidence.iterdir())
    except PermissionError:pass
    else:raise ValueError('root evidence readable')
    sys.path.insert(0,str(root/'vendor'))
    import jwt,uvicorn,starlette,jsonschema,rpds
    from cryptography.hazmat.primitives.asymmetric import rsa
    def load(name):
        spec=importlib.util.spec_from_file_location('protected_probe_'+name,root/'engineering/tools/rras_history_web'/(name+'.py'))
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
    auth=load('access');history=load('history');app_module=load('app')
    config=auth.AccessConfig('https://fixture.cloudflareaccess.com','fixture-audience','operator@example.test','https://history.example.test')
    private=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    public=json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key()));public.update(kid='protected-fixture',alg='RS256',use='sig')
    def deny(message):raise ValueError('history service must not be contacted')
    app=app_module.create_app(history.Reader(['jarvis'],deny),auth.Access(config,auth.Keys(config,lambda:{'keys':[public]})))
    now=int(time.time());token=jwt.encode(dict(iss=config.issuer,aud=[config.audience],email=config.email,sub='fixture',iat=now-1,nbf=now-1,exp=now+60),private,algorithm='RS256',headers={'kid':'protected-fixture'})
    async def request(path,signed):
        headers=[(b'host',b'history.example.test')]
        if signed:headers.append((b'cf-access-jwt-assertion',signed.encode()))
        messages=[]
        async def send(message):messages.append(message)
        async def receive():return {'type':'http.request','body':b'','more_body':False}
        await app(dict(type='http',http_version='1.1',method='GET',scheme='https',path=path,raw_path=path.encode(),query_string=b'',headers=headers,server=('history.example.test',443),client=('127.0.0.1',1)),receive,send)
        return messages[0]['status'],b''.join(item.get('body',b'') for item in messages)
    async def check():
        for path in ('/','/assets/app.js','/api/repositories'):
            denied,_=await request(path,None)
            if denied!=403:raise ValueError('unsigned request accepted')
            status,body=await request(path,token)
            if status!=200 or not body:raise ValueError('authenticated asset/read dispatch failed')
    asyncio.run(asyncio.wait_for(check(),15))
    boot=subprocess.run([sys.executable,'-I','-S','-B',str(root/'engineering/tools/rras_history_web/runtime_entry.py'),'--help'],capture_output=True,timeout=10,env={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','LANG':'C.UTF-8'},cwd='/')
    if boot.returncode or b'--config' not in boot.stdout:raise ValueError('exact bootstrap failed')
    return dict(phase='protected_dashboard_package_probe_verified',probe_uid=61164,
        cases=['root_owned_payload_unwritable','root_evidence_denied','isolated_network_no_groups_capabilities_provider_environment',
            'exact_offline_dependency_imports','generated_signature_and_asset_read_dispatch','missing_assertion_denied','exact_runtime_bootstrap'],
        history_service_contacted=False,cloudflare_contacted=False,listener_started=False,real_credentials_used=False,api_calls=0)


if __name__=='__main__':print(json.dumps(run(*sys.argv[1:])))
