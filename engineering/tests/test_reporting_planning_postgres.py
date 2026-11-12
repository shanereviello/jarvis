"""Opt-in disposable Postgres acceptance; never connects to production."""
import json
import os
from pathlib import Path
import subprocess
import time
import uuid
import pytest


@pytest.mark.skipif(os.environ.get('SHRR_POSTGRES_DOCKER')!='1',reason='disposable PostgreSQL fixture is opt-in')
def test_planning_intake_is_replay_safe_and_partitioned_from_execution():
    name='rras-planning-fixture-'+uuid.uuid4().hex[:12]
    root=Path(__file__).resolve().parents[1]
    def run(args,data=None,ok=True):
        result=subprocess.run(args,input=data,text=True,capture_output=True,timeout=40)
        if ok:assert result.returncode==0,result.stderr[-2000:]
        else:assert result.returncode!=0
        return result.stdout.strip()
    started=False
    try:
        run(['docker','run','-d','--pull=never','--name',name,'--network','none','--read-only','--cap-drop','ALL',
             '--security-opt','no-new-privileges','--user','postgres','--tmpfs','/tmp:rw,nosuid,size=256m,mode=1777',
             '--tmpfs','/var/run/postgresql:rw,nosuid,size=8m,mode=1777','-e','PGDATA=/tmp/pgdata',
             '-e','POSTGRES_HOST_AUTH_METHOD=trust','postgres:18','postgres','-c','listen_addresses='])
        started=True
        for _ in range(40):
            if subprocess.run(['docker','exec',name,'pg_isready','-U','postgres'],capture_output=True).returncode==0:
                time.sleep(1)
                probe=subprocess.run(['docker','exec',name,'psql','-X','-A','-t','-U','postgres','-c','SELECT 1'],capture_output=True)
                if probe.returncode==0 and probe.stdout.strip()==b'1':break
            time.sleep(.25)
        else:raise AssertionError('fixture did not start')
        def sql(text,ok=True):return run(['docker','exec','-i',name,'psql','-X','-A','-t','-v','ON_ERROR_STOP=1','-U','postgres'],text,ok)
        sql('CREATE SCHEMA linear_bridge;'+(root/'contracts/linear-codex-n8n-v1.sql').read_text())
        sql((root/'contracts/linear-codex-planning-v1.sql').read_text())
        ids=[str(uuid.UUID(int=n)) for n in range(1,10)]
        org,app,session,issue,delivery=ids[:5]
        sql(f"INSERT INTO linear_bridge.codex_apps VALUES('{org}','{app}');")
        event=dict(contract='codex-planning-event.v1',mode='planning',organization_id=org,app_user_id=app,
            session_id=session,issue_id=issue,source_key='created:fixture',action='created',message='Fixture',signal=None)
        def accept(delivery_id,value=event):
            raw=json.dumps(value);return f"SELECT inserted FROM linear_bridge.codex_planning_accept('{org}','{app}','{delivery_id}','{'a'*64}',$x${raw}$x$::jsonb);"
        assert sql(accept(delivery))=='t'
        assert sql(accept(delivery))=='f'
        assert sql(accept(ids[5]))=='f'
        sql(accept(ids[6],dict(event,message='changed')),False)
        sql(accept(ids[7],dict(event,binding={})),False)
        sql(f"INSERT INTO linear_bridge.codex_sessions VALUES('{org}','{app}','{session}','{issue}','{{}}');",False)
        sql(f"INSERT INTO linear_bridge.codex_deliveries VALUES('{org}','{app}','{delivery}','{'a'*64}',gen_random_uuid());",False)
        execution=dict(contract='codex-admitted-event.v1',organization_id=org,app_user_id=app,session_id=ids[6],
            issue_id=issue,source_key='created:execution',action='created',binding={'plan_id':'EXISTING'})
        raw=json.dumps(execution)
        assert sql(f"SELECT inserted FROM linear_bridge.codex_accept('{org}','{app}','{ids[7]}','{'b'*64}',$x${raw}$x$::jsonb);")=='t'
        sql(accept(ids[7],dict(event,session_id=ids[8],source_key='created:other')),False)
        sql(accept(ids[8],dict(event,session_id=ids[6],source_key='created:other')),False)
        assert sql('SELECT count(*) FROM linear_bridge.codex_planning_events;')=='1'
        assert sql('SELECT count(*) FROM linear_bridge.codex_planning_outbox;')=='1'
        assert sql('SELECT count(*) FROM linear_bridge.codex_events;')=='1'
    finally:
        if started:subprocess.run(['docker','rm','-f',name],capture_output=True,timeout=30)
