import importlib.util,json,subprocess,uuid
from pathlib import Path
root=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('future_transport',root/'engineering/tools/rras_reporting/hermes_future_transport.py')
t=importlib.util.module_from_spec(spec);spec.loader.exec_module(t)
name='rras-hermes-future-fixture-'+uuid.uuid4().hex[:12]
org='00000000-0000-4000-8000-000000000001';sid='00000000-0000-4000-8000-000000000002';issue='00000000-0000-4000-8000-000000000003';cutoff='2026-01-01T00:00:00Z'
def run(args, **kwargs):
    result=subprocess.run(args,capture_output=True,timeout=90,**kwargs)
    if result.returncode:raise RuntimeError('synthetic fixture command failed: '+result.stderr.decode()[-2000:])
    return result
try:
    run(['docker','run','-d','--rm','--pull=never','--name',name,'--network=none','--read-only','--cap-drop=ALL','--user','1000:1000','--tmpfs','/tmp:rw,nosuid,nodev,size=128m,mode=1777','--tmpfs','/opt/data:rw,nosuid,nodev,size=128m,uid=1000,gid=1000,mode=700','--mount','type=bind,source=/opt/rras-engineering/releases/standardized-history-4b8578d5ddd1,target=/opt/rras-engineering-reporting,readonly','--entrypoint','/usr/bin/sleep',t.IMAGE,'300'])
    init=r'''import sys
from pathlib import Path
sys.path.insert(0,'/opt/hermes');sys.path.insert(0,'/opt/rras-engineering-reporting/engineering/tools/rras_reporting')
from hermes_state import SessionDB
from capture_intake import Spool
p=Path('/opt/data/rras-engineering-capture');p.mkdir(mode=0o700);Spool(p/'spool',create=True)
db=SessionDB(db_path=Path('/opt/data/state.db'));sid='linear:00000000-0000-4000-8000-000000000001:00000000-0000-4000-8000-000000000002'
db.create_session(sid,'api_server');db.append_message(sid,'user','SYNTHETIC-FUTURE-ONLY');db.close()
'''
    run(['docker','exec','--user','1000:1000','-i',name,'/usr/bin/env','-i','PATH=/usr/bin:/bin','HOME=/tmp','HERMES_HOME=/opt/data','LANG=C.UTF-8','/opt/hermes/.venv/bin/python','-I','-B','-'],input=init.encode())
    worker=t.existing_hermes_worker(organization_id=org,cutoff=cutoff,mappings={},authorization_reference='Synthetic fixture',entry_source=(root/'engineering/tools/rras_reporting/hermes_future_native_entry.py').read_bytes(),container=name)
    row={'organization_id':org,'agent_session_id':sid,'issue_id':issue,'hermes_session_id':'linear:'+org+':'+sid,'created_at':'2026-01-01T00:00:01Z'}
    request={'page':{'contract':'hermes-future-session-page.v1','sessions':[row]},'after_time':cutoff,'after_id':'00000000-0000-0000-0000-000000000000'}
    first=worker(request);second=worker(request)
    assert first['sessions'][0]['changed'] and not second['sessions'][0]['changed']
    future=t.existing_hermes_worker(organization_id=org,cutoff='2099-01-01T00:00:00Z',mappings={},authorization_reference='Synthetic fixture',entry_source=(root/'engineering/tools/rras_reporting/hermes_future_native_entry.py').read_bytes(),container=name)
    later=dict(row,created_at='2100-01-01T00:00:00Z')
    try:future({'page':{'contract':'hermes-future-session-page.v1','sessions':[later]},'after_time':'2099-01-01T00:00:00Z','after_id':'00000000-0000-0000-0000-000000000000'})
    except ValueError:pass
    else:raise ValueError('pre-cutoff native session was accepted')
    print(json.dumps({'existing_container_fixture':True,'synthetic_session':True,'replay_deduplicated':True,'native_cutoff_enforced':True,'models_started':0}))
finally:
    subprocess.run(['docker','rm','-f',name],capture_output=True,timeout=30)
