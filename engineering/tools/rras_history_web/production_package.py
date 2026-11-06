"""Exact-commit offline dashboard runtime and inactive plan. No host mutations."""
import email.parser
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import re
import stat
import subprocess

MANIFEST='runtime-manifest.json'
PYTHON='/opt/rras-engineering/releases/cpython-3.13.16-ae7041461525/bin/python3.13'
SOURCE_FILES={f'engineering/tools/rras_history_web/{name}.py' for name in ('access','app','history','entry','runtime_entry')}|{
    f'engineering/tools/rras_history_web/assets/{name}' for name in ('index.html','app.css','app.js')}|{
    'engineering/tools/rras_history/contract.py','engineering/tools/rras_history/unix.py',
    'engineering/contracts/engineering-history-v1.schema.json','engineering/contracts/engineering-history-v2.schema.json','engineering/config/history-web/rras-engineering-history-web.service.in',
    'engineering/requirements-history-web-lock.txt'}
ARTIFACTS={'deployment/rras-engineering-history-web.service','deployment/install-plan.json','deployment/ROLLBACK.md'}
LIMIT=96*1024*1024


def encoded(value):return (json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode()


def decode(raw):
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('duplicate JSON member')
            result[key]=value
        return result
    return json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite JSON')))


def regular(path,limit=32*1024*1024):
    path=Path(path)
    if not path.is_absolute() or path.resolve(strict=True)!=path:raise ValueError('canonical regular input required')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or not 0<=info.st_size<=limit:raise ValueError('bounded regular input required')
        raw=stream.read(limit+1)
    if len(raw)>limit:raise ValueError('input too large')
    return raw


def safe_name(name):
    if type(name) is not str:raise ValueError('path required')
    path=PurePosixPath(name)
    if (str(path)!=name or path.is_absolute() or len(name)>512 or any(p in ('..','.git','__pycache__','bin') for p in path.parts) or
            name.endswith(('.pyc','.pth')) or not(name in SOURCE_FILES or name in ARTIFACTS or name.startswith('vendor/'))):raise ValueError('unsafe runtime path')


def payload_identity(files):
    return hashlib.sha256(encoded({name:hashlib.sha256(raw).hexdigest() for name,raw in sorted(files.items()) if not name.startswith('deployment/')})).hexdigest()


def dependencies(files):
    def normalize(name):return re.sub('[-_.]+','-',name).lower()
    locked={}
    for line in files['engineering/requirements-history-web-lock.txt'].decode().splitlines():
        if not line or line.startswith('#'):continue
        match=re.fullmatch(r'([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+-]+)',line)
        if not match or normalize(match[1]) in locked:raise ValueError('exact dependency lock required')
        locked[normalize(match[1])]=match[2]
    found={}
    for name,raw in files.items():
        if name.startswith('vendor/') and re.fullmatch(r'vendor/[^/]+\.dist-info/METADATA',name):
            message=email.parser.BytesParser().parsebytes(raw)
            package=message.get_all('Name',[]);version=message.get_all('Version',[])
            if len(package)!=1 or len(version)!=1 or normalize(package[0]) in found:raise ValueError('unique dependency metadata required')
            found[normalize(package[0])]=version[0]
    if not locked or found!=locked:raise ValueError('runtime dependency inventory differs')
    return locked


def artifacts(release,digest,template,inventory):
    if not re.fullmatch('/opt/rras-engineering/releases/history-web-[0-9a-f]{12}',release):raise ValueError('exact release required')
    # Allocation/configuration/grants remain a later explicit host decision.
    text='\n'.join(line for line in template.decode().splitlines() if not line.lstrip().startswith('#'))+'\n'
    text=text.replace('@UID@','993').replace('@GID@','993').replace('@RELEASE@',release).replace('@PYTHON@',PYTHON)
    if '@' in text:raise ValueError('unresolved unit template')
    plan=dict(contract='engineering-history-web-install-plan.v1',scope='inactive-preparation-only',release=release,payload_sha256=digest,
        interpreter=PYTHON,interpreter_version='3.13.16',dependency_inventory=inventory,
        account=dict(name='rras-history-web',uid=993,gid=993,selection='tentative-must-be-unused-at-install',home='/nonexistent',shell='/usr/sbin/nologin'),
        config='/etc/rras-engineering-history-web/config.json',configuration_included=False,
        required_operator_fields=['issuer','audience','email','origin','bind','port','repositories'],
        service='rras-engineering-history-web.service',unit_enabled=False,unit_started=False,
        history_socket='/run/rras-engineering-history/service.sock',history_service_uid=995,
        proposed_grant=dict(uid=993,private_read=['jarvis'],write=[]),grant_applied=False,
        stage_authorized=False,activation_authorized=False,cloudflare_change_authorized=False,
        backup_status='deferred-by-operator-no-verified-recovery',
        gates=['separate-source-merge','final-package-host-checks','explicit-inactive-install',
            'operator-selected-protected-config','live-cloudflare-key-verification','connector-route-rehearsal',
            'explicit-grant-service-restart-and-activation','authenticated-browser-acceptance'],
        rollback='stop-disable-dashboard-only-preserve-history-and-spools-no-database-restore')
    rollback=b'''# Disable-only rollback plan

With explicit operator approval, stop and disable only the dashboard unit and
verify its process/listener stopped. Withdraw the exact new Cloudflare route only
through separately reviewed connector/Access configuration. Preserve the private
history/workflow databases, client spools, accounts, release, configuration and
installation evidence. Never roll a database back to repair a UI deployment.
Revoke the dedicated history reader grant through an explicit policy/restart review;
preserve every other principal. Do not restart Hermes or alter coding services.
This document executes no commands and authorizes no installation or recovery.
'''
    return {'deployment/rras-engineering-history-web.service':text.encode(),
        'deployment/install-plan.json':encoded(plan),'deployment/ROLLBACK.md':rollback}


def verify(candidate,expected):
    candidate=Path(candidate)
    if not candidate.is_absolute() or candidate.resolve(strict=True)!=candidate:raise ValueError('canonical candidate required')
    raw=regular(candidate/MANIFEST,512*1024)
    if type(expected) is not str or not re.fullmatch('[0-9a-f]{64}',expected) or hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('manifest changed')
    manifest=decode(raw)
    if (type(manifest) is not dict or set(manifest)!={'contract','source_commit','release','payload_sha256','stage_authorized','activation_authorized','files'} or
            encoded(manifest)!=raw or manifest['contract']!='engineering-history-web-runtime.v1' or
            manifest['stage_authorized'] is not False or manifest['activation_authorized'] is not False or
            type(manifest['source_commit']) is not str or not re.fullmatch('[0-9a-f]{40}',manifest['source_commit']) or
            type(manifest['files']) is not dict or not (SOURCE_FILES|ARTIFACTS)<set(manifest['files']) or len(manifest['files'])>3000):raise ValueError('invalid inactive runtime manifest')
    files={};total=0
    for name,digest in manifest['files'].items():
        safe_name(name)
        if type(digest) is not str or not re.fullmatch('[0-9a-f]{64}',digest):raise ValueError('digest required')
        content=regular(candidate/name);total+=len(content)
        if total>LIMIT or hashlib.sha256(content).hexdigest()!=digest:raise ValueError('runtime payload changed')
        files[name]=content
    inventory=dependencies(files);digest=payload_identity(files);release='/opt/rras-engineering/releases/history-web-'+digest[:12]
    if manifest['payload_sha256']!=digest or manifest['release']!=release:raise ValueError('runtime identity differs')
    for name,content in artifacts(release,digest,files['engineering/config/history-web/rras-engineering-history-web.service.in'],inventory).items():
        if files[name]!=content:raise ValueError('inactive artifact changed')
    return manifest,files


def build(source,vendor,destination,commit):
    source=Path(source).resolve(strict=True);vendor=Path(vendor).resolve(strict=True);destination=Path(destination)
    if type(commit) is not str or not re.fullmatch('[0-9a-f]{40}',commit):raise ValueError('exact source commit required')
    def git(*args):return subprocess.check_output(['/usr/bin/git','-C',str(source),*args],stderr=subprocess.PIPE,
        env={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','LANG':'C.UTF-8','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null'},timeout=30)
    if git('rev-parse','HEAD').decode().strip()!=commit:raise ValueError('source commit differs')
    files={name:git('show',commit+':'+name) for name in SOURCE_FILES}
    for path in sorted(vendor.rglob('*')):
        if path.is_dir() and not path.is_symlink():continue
        parts=path.relative_to(vendor).parts
        if any(p in ('__pycache__','bin') for p in parts) or path.suffix=='.pyc':continue
        name='vendor/'+path.relative_to(vendor).as_posix();safe_name(name);files[name]=regular(path)
    inventory=dependencies(files);digest=payload_identity(files);release='/opt/rras-engineering/releases/history-web-'+digest[:12]
    files.update(artifacts(release,digest,files['engineering/config/history-web/rras-engineering-history-web.service.in'],inventory))
    if len(files)>3000 or sum(map(len,files.values()))>LIMIT:raise ValueError('runtime bounds exceeded')
    if not destination.is_absolute() or destination.parent.resolve(strict=True)!=destination.parent:raise ValueError('canonical destination required')
    manifest=dict(contract='engineering-history-web-runtime.v1',source_commit=commit,release=release,payload_sha256=digest,
        stage_authorized=False,activation_authorized=False,files={name:hashlib.sha256(content).hexdigest() for name,content in sorted(files.items())})
    destination.mkdir(mode=0o700)
    for name,content in files.items():
        path=destination/name;path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        with path.open('xb') as stream:os.fchmod(stream.fileno(),0o600);stream.write(content)
    raw=encoded(manifest)
    with (destination/MANIFEST).open('xb') as stream:os.fchmod(stream.fileno(),0o600);stream.write(raw)
    sha=hashlib.sha256(raw).hexdigest();verify(destination,sha)
    return dict(phase='inactive_dashboard_package_built',release=release,manifest_sha256=sha,source_commit=commit,
        files=len(files),stage_authorized=False,activation_authorized=False,host_mutations=False)
