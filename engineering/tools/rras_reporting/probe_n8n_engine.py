"""Disposable n8n engine acceptance. Synthetic credentials; no production mounts."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import time
import uuid

ROOT=Path(__file__).resolve().parents[2]


def run(argv,data=None,timeout=50):
    result=subprocess.run(argv,input=data,text=True,capture_output=True,timeout=timeout)
    if result.returncode:
        raise ValueError('Fixture command failed '+str(result.returncode)+' '+repr(argv[-3:])+': '+result.stderr[-1600:]+result.stdout[-1600:])
    return result.stdout


def probe():
    key=uuid.uuid4().hex[:12];pg='rras-codex-engine-pg-'+key;n8n='rras-codex-engine-'+key
    created=[]
    try:
        run(['docker','run','-d','--pull=never','--name',pg,'--network','none','--read-only',
            '--cap-drop','ALL','--security-opt','no-new-privileges','--user','postgres',
            '--tmpfs','/tmp:rw,nosuid,size=384m,mode=1777',
            '--tmpfs','/var/run/postgresql:rw,nosuid,size=8m,mode=1777',
            '-e','PGDATA=/tmp/engine-fixture/pgdata','-e','POSTGRES_HOST_AUTH_METHOD=trust',
            'postgres:18','postgres','-c','listen_addresses=127.0.0.1'])
        created.append(pg)
        for _ in range(60):
            ready=subprocess.run(['docker','exec',pg,'pg_isready','-U','postgres'],capture_output=True)
            if ready.returncode==0:break
            time.sleep(.25)
        else:raise ValueError('Fixture PostgreSQL did not become ready')
        def sql(query):
            return run(['docker','exec','-i',pg,'psql','-X','-A','-t','-v','ON_ERROR_STOP=1','-U','postgres'],query)
        sql('CREATE SCHEMA linear_bridge;\n'+(ROOT/'contracts/linear-codex-n8n-v1.sql').read_text())
        sql("CREATE ROLE codex_transport LOGIN; GRANT USAGE ON SCHEMA linear_bridge TO codex_transport;"
            "GRANT SELECT,UPDATE ON linear_bridge.codex_apps TO codex_transport;"
            "GRANT SELECT,INSERT,UPDATE ON linear_bridge.codex_sessions,linear_bridge.codex_events,linear_bridge.codex_deliveries,linear_bridge.codex_outbox TO codex_transport;"
            "GRANT EXECUTE ON FUNCTION linear_bridge.codex_accept(uuid,uuid,uuid,text,jsonb) TO codex_transport;"
            "CREATE TABLE linear_bridge.jarvis_fixture(value text);INSERT INTO linear_bridge.jarvis_fixture VALUES('preserve');")
        run(['docker','run','-d','--pull=never','--name',n8n,'--network','container:'+pg,
            '--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--user','node',
            '--tmpfs','/home/node/.n8n:rw,nosuid,size=256m,uid=1000,gid=1000,mode=0700',
            '--tmpfs','/tmp:rw,nosuid,size=128m,uid=1000,gid=1000,mode=1777',
            '--tmpfs','/home/node/.cache:rw,nosuid,size=128m,uid=1000,gid=1000,mode=0700',
            '-e','DB_TYPE=postgresdb','-e','DB_POSTGRESDB_HOST=127.0.0.1','-e','DB_POSTGRESDB_PORT=5432',
            '-e','DB_POSTGRESDB_DATABASE=postgres','-e','DB_POSTGRESDB_USER=postgres',
            '-e','N8N_ENCRYPTION_KEY=synthetic-engine-fixture-key-at-least-32',
            '-e','NODE_OPTIONS=--max-old-space-size=512',
            '-e','N8N_DIAGNOSTICS_ENABLED=false','-e','N8N_VERSION_NOTIFICATIONS_ENABLED=false',
            '-e','N8N_PERSONALIZATION_ENABLED=false','-e','N8N_SECURE_COOKIE=false',
            'docker.n8n.io/n8nio/n8n:2.28.3'])
        created.append(n8n)
        def node(script,data=None):return run(['docker','exec','--user','node','-i',n8n,'node','-e',script],data)
        cookie=''
        def request(path,body=None,headers=None,port=5678):
            options=dict(method='GET' if body is None else 'POST',headers=dict(headers or {}),redirect='manual')
            if cookie and port==5678:options['headers']['Cookie']=cookie
            if body is not None:
                options['headers']['Content-Type']='application/json';options['body']=json.dumps(body)
            return json.loads(node("const fs=require('node:fs');const o=JSON.parse(fs.readFileSync(0,'utf8'));"
                "o.options.signal=AbortSignal.timeout(5000);fetch(o.url,o.options).then(async r=>console.log(JSON.stringify({status:r.status,body:await r.text(),cookies:r.headers.getSetCookie()})))"
                ".catch(e=>{console.error(e.message);process.exitCode=1;});",json.dumps(dict(url='http://127.0.0.1:'+str(port)+path,options=options))))
        for _ in range(120):
            try:
                response=request('/rest/settings')
                if response['status']==200 and 'data' in json.loads(response['body']):break
            except ValueError:pass
            time.sleep(.5)
        else:
            raise ValueError('Fixture n8n did not become ready: '+run(['docker','inspect','--format','{{json .State}}',n8n])+run(['docker','logs','--tail','20',n8n]))
        setup=request('/rest/owner/setup',dict(email='fixture@example.invalid',firstName='Fixture',lastName='Owner',password='SyntheticFixture12!'))
        assert setup['status']==200,setup
        login=request('/rest/login',dict(emailOrLdapLoginId='fixture@example.invalid',password='SyntheticFixture12!'))
        assert login['status']==200,login
        cookie='; '.join(x.split(';')[0] for x in login['cookies'])
        assert cookie, 'Fixture owner session cookie missing: '+repr(login)+repr(setup)
        spec=importlib.util.spec_from_file_location('engine_inputs',ROOT/'tools/rras_reporting/probe_n8n_codex.py')
        p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
        spec=importlib.util.spec_from_file_location('engine_render',ROOT/'tools/rras_reporting/n8n_codex.py')
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        c=p.fixture();c['runtime_origin']='http://127.0.0.1:8899/runtime';package=m.render(c)
        sql("INSERT INTO linear_bridge.codex_apps VALUES('"+c['organization_id']+"','"+c['app_user_id']+"');")
        creds=[dict(id=c['credentials']['postgres'],name='Fixture SQL',type='postgres',data=dict(host='127.0.0.1',port=5432,database='postgres',user='codex_transport',password='synthetic',ssl='disable')),
            dict(id=c['credentials']['edge_header'],name='Fixture edge',type='httpHeaderAuth',data=dict(name='X-RRAS-Codex-Bridge',value='synthetic-edge-bridge')),
            dict(id=c['credentials']['runtime_header'],name='Fixture runtime',type='httpHeaderAuth',data=dict(name='Authorization',value='Bearer synthetic-runtime-bridge')),
            dict(id=c['credentials']['codex_oauth'],name='Fixture OAuth',type='oAuth2Api',data=dict(grantType='authorizationCode',authUrl='http://127.0.0.1:8899/authorize',accessTokenUrl='http://127.0.0.1:8899/token',clientId=c['oauth_client_id'],clientSecret='synthetic',scope='read write app:mentionable app:assignable',authentication='body',oauthTokenData=dict(access_token='synthetic-oauth-token',token_type='Bearer',expires_in=86400)))]
        def write(path,value):
            node("require('node:fs').writeFileSync("+json.dumps(path)+",require('node:fs').readFileSync(0),{mode:0o600});",json.dumps(value))
        def api(path,body):
            response=request(path,body)
            assert response['status'] in (200,201),response
            result=json.loads(response['body'])
            assert 'data' in result,result
            return result['data']
        credential_refs={}
        for credential in creds:
            old=credential.pop('id')
            credential_refs[old]=api('/rest/credentials',credential)['id']
        ids={}
        workflows={}
        for name,w in package['workflows'].items():
            ids[name]=uuid.uuid4().hex[:16];w['id']=ids[name]
            # Fixture observability only; schedules are triggered manually below.
            w['settings'].update(saveDataErrorExecution='all',saveDataSuccessExecution='all',saveManualExecutions=True,saveExecutionProgress=True)
            for n in w['nodes']:
                if n['type']=='n8n-nodes-base.scheduleTrigger':
                    n['type']='n8n-nodes-base.manualTrigger';n['typeVersion']=1;n['parameters']={}
                if n['type']=='n8n-nodes-base.httpRequest' and n['parameters']['url']=='https://api.linear.app/graphql':
                    n['parameters']['url']='http://127.0.0.1:8899/graphql'
                for ref in n.get('credentials',{}).values():ref['id']=credential_refs[ref['id']]
            print('Importing fixture '+name,flush=True)
            workflows[name]=api('/rest/workflows',w)
        remote=r"""const http=require('node:http');const state={calls:[],activities:[],requests:[],interrupts:[],active:null,complete:false,uncertain:false,losePublication:false,wrongActor:false};
const uid=n=>'00000000-0000-0000-0000-'+String(n).padStart(12,'0');
http.createServer(async(req,res)=>{let raw='';for await(const x of req)raw+=x;let b=raw?JSON.parse(raw):{};
state.requests.push({url:req.url,authorization:req.headers.authorization,query:b.query});
const reply=(status,v)=>{res.writeHead(status,{'Content-Type':'application/json'});res.end(JSON.stringify(v));};
if(req.url==='/fixture/status')return reply(200,state);
if(req.url==='/fixture/complete'){state.complete=true;return reply(200,{ok:true});}
if(req.url==='/fixture/uncertain'){state.uncertain=true;return reply(200,{ok:true});}
if(req.url==='/fixture/lose-publication'){state.losePublication=true;return reply(200,{ok:true});}
if(req.url==='/fixture/wrong-actor'){state.wrongActor=true;return reply(200,{ok:true});}
if(req.url==='/graphql'){
if(req.headers.authorization!=='Bearer synthetic-oauth-token')return reply(403,{error:'fixture OAuth denied'});
if(b.query.startsWith('query '))return reply(200,{data:{viewer:{id:uid(state.wrongActor?20:2),organization:{id:uid(1)}}}});
state.activities.push(b.variables.input);if(state.losePublication){state.losePublication=false;return res.destroy();}
return reply(200,{data:{agentActivityCreate:{success:true,agentActivity:{id:b.variables.input.id}}}});}
if(req.headers.authorization!=='Bearer synthetic-runtime-bridge')return reply(403,{error:'fixture runtime denied'});
if(req.url==='/runtime/v1/dispatch'){state.calls.push(b);state.active=b.dispatch_id;state.complete=false;state.uncertain=false;return reply(202,{dispatch:b.dispatch_id,state:'running'});}
if(req.url==='/runtime/v1/interrupt'){state.interrupts.push(b.dispatch_id);return reply(200,{dispatch:b.dispatch_id,state:'interrupted'});}
if(req.url.startsWith('/runtime/v1/runs/')){const id=req.url.split('/').pop();return reply(200,{dispatch:id,state:state.interrupts.includes(id)?'interrupted':state.complete?'completed':state.uncertain?'uncertain':'running',result:'Synthetic final result'});}
reply(404,{error:'unknown fixture route'});
}).listen(8899,'127.0.0.1');"""
        node("require('node:fs').writeFileSync('/tmp/remote.cjs',require('node:fs').readFileSync(0));",remote)
        run(['docker','exec','--user','node','-d',n8n,'node','/tmp/remote.cjs'])
        api('/rest/workflows/'+ids['inbound']+'/activate',dict(versionId=workflows['inbound']['versionId']))
        path='/webhook/rras-codex-agent-events'
        for _ in range(40):
            response=request(path,{},dict({'X-RRAS-Codex-Bridge':'wrong'}))
            if response['status']!=404:break
            time.sleep(.5)
        assert response['status']==403,response
        body=dict(type='AgentSessionEvent',action='created',organizationId=c['organization_id'],oauthClientId=c['oauth_client_id'],webhookTimestamp=int(time.time()*1000),agentSession=dict(id=str(uuid.UUID(int=5)),issue=dict(id=str(uuid.UUID(int=4))),creatorId=str(uuid.UUID(int=6))),promptContext='Synthetic engine-only request')
        raw=json.dumps(body)
        headers={'X-RRAS-Codex-Bridge':'synthetic-edge-bridge','X-RRAS-Codex-Verified':'v1','Linear-Delivery':str(uuid.UUID(int=7)),'X-RRAS-Codex-Body-Sha256':hashlib.sha256(raw.encode()).hexdigest()}
        first=request(path,body,headers);assert first['status']==200,first
        assert json.loads(first['body'])['inserted'] is True,first
        again=request(path,body,headers);assert again['status']==200,again
        assert json.loads(again['body'])['inserted'] is False,again
        assert sql('SELECT count(*) FROM linear_bridge.codex_events;').strip()=='1'
        assert sql('SELECT count(*) FROM linear_bridge.codex_outbox;').strip()=='1'
        def execute(which):
            result=api('/rest/workflows/'+ids[which]+'/run',dict(triggerToStartFrom=dict(name='Poll Codex transport')))
            assert 'executionId' in result,result
            for _ in range(100):
                status=sql("SELECT status FROM execution_entity WHERE id="+str(int(result['executionId']))+";").strip()
                if status not in ('new','running','waiting'):break
                time.sleep(.25)
            assert status in ('success',''), 'Engine execution failed: '+which+' '+status+' '+sql('SELECT left(data,14000) FROM execution_data ORDER BY \"executionId\" DESC LIMIT 1;')+' '+repr(request('/fixture/status',port=8899))
        execute('outbound')
        assert sql("SELECT count(*) FROM linear_bridge.codex_outbox WHERE state='sent';").strip()=='1', sql('SELECT data FROM execution_data ORDER BY \"executionId\" DESC LIMIT 1;')+' '+repr(request('/fixture/status',port=8899))
        execute('dispatch')
        assert sql("SELECT count(*) FROM linear_bridge.codex_events WHERE state='running';").strip()=='1'
        execute('reconcile')
        request('/fixture/uncertain',{},port=8899)
        execute('reconcile');execute('outbound')
        assert sql("SELECT count(*) FROM linear_bridge.codex_events WHERE state='uncertain';").strip()=='1'
        execute('reconcile')
        assert sql('SELECT count(*) FROM linear_bridge.codex_outbox;').strip()=='2'
        request('/fixture/complete',{},port=8899)
        execute('reconcile');execute('outbound')
        assert sql("SELECT count(*) FROM linear_bridge.codex_events WHERE state='completed';").strip()=='1'
        assert sql("SELECT count(*) FROM linear_bridge.codex_outbox WHERE state='sent';").strip()=='3'
        status=json.loads(request('/fixture/status',port=8899)['body'])
        assert len(status['calls'])==1 and len(status['activities'])==3,status
        assert status['activities'][1]['content']['type']=='thought'
        assert status['activities'][-1]['content']['body']=='Synthetic final result'

        def deliver(session,delivery,activity=None,signal=None):
            value=dict(body,webhookTimestamp=int(time.time()*1000),
                agentSession=dict(body['agentSession'],id=str(uuid.UUID(int=session))))
            if activity is not None:
                value['action']='prompted'
                value['agentActivity']=dict(id=str(uuid.UUID(int=activity)),agentSessionId=str(uuid.UUID(int=session)),
                    userId=str(uuid.UUID(int=6)),content=dict(type='prompt',body='Synthetic follow-up'))
                if signal:value['agentActivity']['signal']=signal
            hs=dict(headers);hs['Linear-Delivery']=str(uuid.UUID(int=delivery))
            hs['X-RRAS-Codex-Body-Sha256']=hashlib.sha256(json.dumps(value).encode()).hexdigest()
            response=request(path,value,hs);assert response['status']==200,response
            return json.loads(response['body'])['event_id']
        current=deliver(50,51);execute('dispatch')
        follow=deliver(50,52,52);execute('dispatch')
        assert sql("SELECT state FROM linear_bridge.codex_events WHERE id='"+follow+"';").strip()=='pending'
        stop=deliver(50,53,53,'stop');execute('dispatch')
        status=json.loads(request('/fixture/status',port=8899)['body'])
        assert len(status['calls'])==2 and status['interrupts']==[current],status
        execute('reconcile')
        assert sql("SELECT state FROM linear_bridge.codex_events WHERE id='"+current+"';").strip()=='interrupted'
        assert sql("SELECT count(*) FROM linear_bridge.codex_outbox WHERE source_key LIKE 'result:"+stop+":%';").strip()=='0'
        execute('outbound');execute('outbound')
        execute('dispatch')
        status=json.loads(request('/fixture/status',port=8899)['body'])
        assert len(status['calls'])==3 and status['calls'][-1]['dispatch_id']==follow,status
        request('/fixture/complete',{},port=8899);execute('reconcile');execute('outbound')

        def reply_row(key):
            return sql("INSERT INTO linear_bridge.codex_outbox(organization_id,app_user_id,session_id,source_key,content) VALUES('"+
                c['organization_id']+"','"+c['app_user_id']+"','"+str(uuid.UUID(int=5))+"','"+key+"','{\"type\":\"thought\",\"body\":\"Fixture only\"}') RETURNING id;").splitlines()[0].strip()
        lost=reply_row('fixture-lost-publication');request('/fixture/lose-publication',{},port=8899)
        execute('outbound')
        assert sql("SELECT state FROM linear_bridge.codex_outbox WHERE id='"+lost+"';").strip()=='uncertain'
        before=json.loads(request('/fixture/status',port=8899)['body']);execute('outbound')
        after=json.loads(request('/fixture/status',port=8899)['body'])
        assert before['activities']==after['activities']
        refused=reply_row('fixture-wrong-actor');request('/fixture/wrong-actor',{},port=8899);execute('outbound')
        assert sql("SELECT state FROM linear_bridge.codex_outbox WHERE id='"+refused+"';").strip()=='dead_letter'
        assert len(json.loads(request('/fixture/status',port=8899)['body'])['activities'])==len(after['activities'])
        assert sql('SELECT value FROM linear_bridge.jarvis_fixture;').strip()=='preserve'
        try:sql('SET ROLE codex_transport; SELECT * FROM linear_bridge.jarvis_fixture;')
        except ValueError:pass
        else:raise ValueError('Transport could read the Jarvis sentinel')
        print(json.dumps(dict(n8n_version='2.28.3',actual_import=True,actual_http_webhook=True,header_denial=True,durable_receipt=True,duplicate_receipt=True,initial_activity=True,exact_single_dispatch=True,runtime_reconcile=True,uncertain_then_final=True,follow_up_serialized=True,matching_turn_stop=True,one_cancellation_result=True,lost_publication_no_resend=True,wrong_oauth_actor_refused=True,final_activity=True,role_grants=True,jarvis_sentinel_preserved=True,network='isolated container namespace',production_mounts=False,real_credentials=False,paid_model_calls=0)))
    finally:
        for name in reversed(created):
            subprocess.run(['docker','rm','-f',name],capture_output=True,timeout=30)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--isolated-containers',action='store_true',required=True)
    parser.parse_args();probe()
