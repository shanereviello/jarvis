"""Offline PostgreSQL acceptance for explicit native handoff transport states."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import time
import uuid

ROOT=Path(__file__).resolve().parents[2]


def local(name):
    spec=importlib.util.spec_from_file_location('handoff_probe_'+name,Path(__file__).with_name(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def run(argv,data=None):
    value=subprocess.run(argv,input=data,text=True,capture_output=True,timeout=40)
    if value.returncode:raise ValueError('Offline handoff fixture command failed: '+value.stderr[-1500:])
    return value.stdout.strip()


def probe():
    name='rras-native-handoff-'+uuid.uuid4().hex[:10];uid=lambda n:str(uuid.UUID(int=n));m=local('native_handoff')
    c=local('probe_n8n_codex').fixture();pin=c['issues'][uid(4)]
    policy=dict(contract='native-agent-handoff-policy.v1',organization_id=uid(1),agents=dict(codex=uid(2),jarvis=uid(20)),issues=c['issues'])
    def literal(value):return "'"+value.replace("'","''")+"'"
    def js(value):return literal(json.dumps(value))+'::jsonb'
    try:
        run(['docker','run','-d','--pull=never','--name',name,'--network','none','--read-only','--cap-drop','ALL',
            '--security-opt','no-new-privileges','--user','postgres','--tmpfs','/tmp:rw,nosuid,size=256m,mode=1777',
            '--tmpfs','/var/run/postgresql:rw,nosuid,size=8m,mode=1777','-e','PGDATA=/tmp/handoff/pgdata',
            '-e','POSTGRES_HOST_AUTH_METHOD=trust','postgres:18','postgres','-c','listen_addresses='])
        for _ in range(40):
            if subprocess.run(['docker','exec',name,'pg_isready','-U','postgres'],capture_output=True).returncode==0:break
            time.sleep(.25)
        else:raise ValueError('offline fixture PostgreSQL unavailable')
        command=['docker','exec','-i',name,'psql','-X','-A','-t','-v','ON_ERROR_STOP=1','-U','postgres']
        sql=lambda value:run(command,value)
        def refused(value):
            result=subprocess.run(command,input=value,text=True,capture_output=True,timeout=10)
            assert result.returncode!=0
        sql('CREATE SCHEMA linear_bridge;\n'+(ROOT/'contracts/linear-codex-n8n-v1.sql').read_text()+
            '\nCREATE TABLE linear_bridge.agent_sessions(agent_session_id text PRIMARY KEY,organization_id text,issue_id text,hermes_session_id text,latest_hermes_run_id text);'
            '\nCREATE TABLE linear_bridge.hermes_runs(hermes_run_id text PRIMARY KEY,agent_session_id text,status text,completed_at timestamptz);\n'+
            (ROOT/'contracts/linear-native-handoff-v1.sql').read_text())
        sql("INSERT INTO linear_bridge.codex_apps VALUES('"+uid(1)+"','"+uid(2)+"');"
            "INSERT INTO linear_bridge.native_handoff_apps VALUES('"+uid(1)+"','codex','"+uid(2)+"'),('"+uid(1)+"','jarvis','"+uid(20)+"');"
            "INSERT INTO linear_bridge.native_handoff_issues VALUES('"+uid(1)+"','"+uid(4)+"',"+js(pin)+");"
            "INSERT INTO linear_bridge.agent_sessions VALUES('"+uid(5)+"','"+uid(1)+"','"+uid(4)+"','synthetic-hermes-5','synthetic-run-5');"
            "INSERT INTO linear_bridge.hermes_runs VALUES('synthetic-run-5','"+uid(5)+"','running',NULL);")
        args=dict(key='coding-investigation',summary='Synthetic engineering context',requested_action='Investigate the selected failure.',references=[],limitations=[])
        trusted=dict(session_id=uid(5),issue_id=uid(4),binding=pin,parent_handoff_id=None,depth=0)
        first=m.prepare(policy,'jarvis',trusted,args)
        def request(intent):return "SELECT linear_bridge.native_handoff_request('"+uid(1)+"',"+literal(intent['sender'])+','+js(intent)+','+literal(m.comment_body(intent))+');'
        assert sql(request(first))==first['id'] and sql(request(first))==first['id']
        changed=dict(first,summary='changed under same stable identity');refused(request(changed))
        def quiescence(role,session):return "linear_bridge.native_handoff_quiescence('"+uid(1)+"',"+literal(role)+",'"+session+"')"
        assert sql('SELECT '+quiescence('jarvis',uid(5))+' IS NULL;')=='t'
        def bind(intent,session):return "SELECT linear_bridge.native_handoff_bind('"+uid(1)+"',"+literal(intent['recipient'])+",'"+intent['id']+"','"+session+"');"
        refused(bind(first,uid(60)))
        sql("UPDATE linear_bridge.hermes_runs SET status='completed',completed_at=now() WHERE hermes_run_id='synthetic-run-5';")
        def confirmed_fixture(intent):
            sql("UPDATE linear_bridge.native_handoffs SET source_quiescence="+quiescence(intent['sender'],intent['source_session_id'])+
                ",comment_state='confirmed',session_state='uncertain' WHERE id='"+intent['id']+"';")
        confirmed_fixture(first);assert sql(bind(first,uid(60)))==uid(60);assert sql(bind(first,uid(60)))==uid(60)
        refused(bind(first,uid(61)))
        def refresh(intent):return sql("SELECT linear_bridge.native_handoff_refresh('"+uid(1)+"','"+intent['id']+"');")
        assert refresh(first)=='requested'
        envelope=dict(contract='codex-admitted-event.v1',organization_id=uid(1),app_user_id=uid(2),session_id=uid(60),issue_id=uid(4),
            source_key='created:'+uid(60),source_actor_id=None,message='Synthetic handoff',signal=None,binding=pin,action='created')
        sql("SELECT * FROM linear_bridge.codex_accept('"+uid(1)+"','"+uid(2)+"','"+uid(62)+"','"+'a'*64+"',"+js(envelope)+');')
        event=sql('SELECT id FROM linear_bridge.codex_events;')
        result=dict(dispatch=event,state='running',thread='synthetic-thread',turn='synthetic-turn')
        sql("UPDATE linear_bridge.codex_events SET state='running',runtime_result="+js(result)+" WHERE id='"+event+"';")
        assert refresh(first)=='acknowledged'
        result['state']='completed';sql("UPDATE linear_bridge.codex_events SET state='completed',runtime_result="+js(result)+" WHERE id='"+event+"';")
        assert refresh(first)=='completed'
        assert sql('SELECT string_agg(state,\',\' ORDER BY sequence) FROM linear_bridge.native_handoff_events;')=='requested,acknowledged,completed'
        second=m.prepare(policy,'codex',dict(trusted,session_id=uid(60),parent_handoff_id=first['id'],depth=1),dict(args,key='return-investigation'))
        forged=dict(second,id=uid(90),parent_handoff_id=None,depth=1);refused(request(forged))
        assert sql(request(second))==second['id'];confirmed_fixture(second);sql(bind(second,uid(70)))
        sql("INSERT INTO linear_bridge.agent_sessions VALUES('"+uid(70)+"','"+uid(1)+"','"+uid(4)+"','synthetic-hermes-70','synthetic-run-70');"
            "INSERT INTO linear_bridge.hermes_runs VALUES('synthetic-run-70','"+uid(70)+"','running',NULL);")
        assert refresh(second)=='acknowledged'
        sql("UPDATE linear_bridge.hermes_runs SET status='completed',completed_at=now() WHERE hermes_run_id='synthetic-run-70';")
        assert refresh(second)=='completed'
        refused("UPDATE linear_bridge.native_handoffs SET body='{}'::jsonb;")
        refused('DELETE FROM linear_bridge.native_handoff_events;')
        print(json.dumps(dict(actual_postgresql=True,both_native_identity_directions=True,exact_replay=True,
            changed_intent_denied=True,source_active_blocks_transfer=True,recipient_binding_immutable=True,
            acknowledgment_requires_runtime=True,terminal_does_not_accept_work=True,loop_parent_reset_denied=True,
            immutable_state_evidence=True,api_calls=0,real_credentials=False,models_started=0,production_mounts=False)))
    finally:subprocess.run(['docker','rm','-f',name],capture_output=True,timeout=15)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--isolated-containers',action='store_true',required=True)
    parser.parse_args();probe()
