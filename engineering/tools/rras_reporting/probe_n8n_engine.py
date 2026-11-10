"""Disposable n8n engine acceptance. Synthetic credentials; no production mounts."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import time
import uuid

ROOT=Path(__file__).resolve().parents[2]


def run(argv,data=None,timeout=50):
    result=subprocess.run(argv,input=data,text=True,capture_output=True,timeout=timeout)
    if result.returncode:
        raise ValueError('Fixture command failed '+str(result.returncode)+' '+repr(argv[-3:])+': '+result.stderr[-1600:]+result.stdout[-1600:])
    return result.stdout


def jarvis_fixture(configuration):
    """Synthetic legacy shape, with the same no-terminal run restrictions."""
    def node(name,kind,parameters,credentials=None):
        value=dict(id=uuid.uuid4().hex,name=name,type='n8n-nodes-base.'+kind,
            typeVersion={'webhook':2.1,'code':2,'httpRequest':4.2,'postgres':2.6}[kind],position=[0,0],parameters=parameters)
        if credentials:value['credentials']=credentials
        return value
    normal="""const raw=$input.first().json.body,session=raw.agentSession,body=raw;
const issue = session.issue ?? body.issue ?? {};
return [{json:{organizationId:raw.organizationId,agentSessionId:session.id,issueId:issue.id,deliveryId:raw.deliveryId,
action:raw.action,prompt:raw.promptContext,rawPayload:raw}}];"""
    nodes=[node('Fixture Jarvis webhook','webhook',dict(httpMethod='POST',path='fixture-jarvis-inbound',responseMode='onReceived',
        authentication='headerAuth',options={}),{'httpHeaderAuth':{'id':'fixture-jarvis-handoff'}}),
        node('Normalize and Validate','code',dict(mode='runOnceForAllItems',jsCode=normal)),
        node('Only New Deliveries','code',dict(mode='runOnceForAllItems',jsCode='return $input.all();')),
        node('Start Restricted Hermes Run','httpRequest',dict(method='POST',url='http://hermes:8642/v1/runs',sendBody=True,
            contentType='raw',rawContentType='application/json',options=dict(timeout=10000),body="={{ JSON.stringify({ input: $('Normalize and Validate').first().json.prompt, session_id: 'linear:'+ $('Normalize and Validate').first().json.organizationId+':'+$('Normalize and Validate').first().json.agentSessionId, instructions: 'You are not authorized to modify repositories, run terminal commands, access files, deploy, merge, push, or create an execution request.' }) }}")),
        node('Record Hermes Run','postgres',dict(operation='executeQuery',query="""WITH session AS (
 INSERT INTO linear_bridge.agent_sessions VALUES($1,$2,$3,$4,$5)
 ON CONFLICT(agent_session_id) DO UPDATE SET latest_hermes_run_id=EXCLUDED.latest_hermes_run_id RETURNING *)
 INSERT INTO linear_bridge.hermes_runs VALUES($5,$1,'running',NULL,$6::uuid) ON CONFLICT DO NOTHING RETURNING hermes_run_id""",
            options=dict(queryReplacement="={{ [$('Normalize and Validate').first().json.agentSessionId,$('Normalize and Validate').first().json.organizationId,$('Normalize and Validate').first().json.issueId,'linear:'+ $('Normalize and Validate').first().json.organizationId+':'+$('Normalize and Validate').first().json.agentSessionId,$json.run_id,$('Normalize and Validate').first().json.deliveryId] }}")),
            {'postgres':{'id':configuration['credentials']['postgres']}})]
    return dict(name='Synthetic existing Jarvis inbound',active=False,nodes=nodes,
        connections={a['name']:dict(main=[[dict(node=b['name'],type='main',index=0)]]) for a,b in zip(nodes,nodes[1:])},
        settings=dict(executionOrder='v1',saveDataSuccessExecution='none',saveDataErrorExecution='none'))


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
        sql('CREATE TABLE linear_bridge.agent_sessions(agent_session_id text PRIMARY KEY,organization_id text,issue_id text,hermes_session_id text,latest_hermes_run_id text);'
            'CREATE TABLE linear_bridge.hermes_runs(hermes_run_id text PRIMARY KEY,agent_session_id text,status text,completed_at timestamptz,delivery_id uuid);'
            +(ROOT/'contracts/linear-native-handoff-v1.sql').read_text())
        sql((ROOT/'contracts/linear-jarvis-engineering-admission-v1.sql').read_text())
        sql("CREATE ROLE codex_transport LOGIN; GRANT USAGE ON SCHEMA linear_bridge TO codex_transport;"
            "GRANT SELECT,UPDATE ON linear_bridge.codex_apps TO codex_transport;"
            "GRANT SELECT,INSERT,UPDATE ON linear_bridge.codex_sessions,linear_bridge.codex_events,linear_bridge.codex_deliveries,linear_bridge.codex_outbox TO codex_transport;"
            "GRANT EXECUTE ON FUNCTION linear_bridge.codex_accept(uuid,uuid,uuid,text,jsonb) TO codex_transport;"
            "GRANT SELECT,UPDATE ON linear_bridge.native_handoffs TO codex_transport;"
            "GRANT SELECT,INSERT ON linear_bridge.native_handoff_events TO codex_transport;"
            "GRANT USAGE,SELECT ON SEQUENCE linear_bridge.native_handoff_events_sequence_seq TO codex_transport;"
            "GRANT EXECUTE ON FUNCTION linear_bridge.native_handoff_bind(uuid,text,uuid,uuid) TO codex_transport;"
            "GRANT SELECT ON linear_bridge.native_handoff_apps,linear_bridge.native_handoff_issues TO codex_transport;"
            "GRANT INSERT ON linear_bridge.native_handoffs TO codex_transport;"
            "GRANT SELECT ON linear_bridge.agent_sessions,linear_bridge.hermes_runs TO codex_transport;"
            "GRANT EXECUTE ON FUNCTION linear_bridge.native_handoff_request(uuid,text,jsonb,text),linear_bridge.native_handoff_quiescence(uuid,text,uuid),linear_bridge.native_handoff_refresh(uuid,uuid) TO codex_transport;"
            "GRANT SELECT,INSERT ON linear_bridge.jarvis_engineering_admissions TO codex_transport;"
            "GRANT USAGE,SELECT ON SEQUENCE linear_bridge.jarvis_engineering_admissions_sequence_seq TO codex_transport;"
            "GRANT EXECUTE ON FUNCTION linear_bridge.jarvis_engineering_admit(uuid,uuid,uuid,uuid,boolean,jsonb,jsonb,uuid) TO codex_transport;"
            "GRANT SELECT,INSERT ON linear_bridge.jarvis_engineering_runs TO codex_transport;"
            "GRANT USAGE,SELECT ON SEQUENCE linear_bridge.jarvis_engineering_runs_sequence_seq TO codex_transport;"
            "GRANT EXECUTE ON FUNCTION linear_bridge.jarvis_engineering_run_bind(text,uuid) TO codex_transport;"
            "GRANT SELECT,INSERT ON linear_bridge.jarvis_engineering_checkpoints TO codex_transport;"
            "GRANT USAGE,SELECT ON SEQUENCE linear_bridge.jarvis_engineering_checkpoints_sequence_seq TO codex_transport;"
            "GRANT EXECUTE ON FUNCTION linear_bridge.jarvis_engineering_checkpoint(uuid,uuid,uuid,text,text,text) TO codex_transport;"
            "GRANT INSERT,UPDATE ON linear_bridge.agent_sessions,linear_bridge.hermes_runs TO codex_transport;"
            "CREATE TABLE linear_bridge.outbox(idempotency_key text UNIQUE,agent_session_id text,event_type text,payload jsonb);"
            "GRANT INSERT ON linear_bridge.outbox TO codex_transport;"
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
        spec=importlib.util.spec_from_file_location('engine_handoff',ROOT/'tools/rras_reporting/n8n_handoff.py')
        hm=importlib.util.module_from_spec(spec);spec.loader.exec_module(hm)
        handoff_policy=dict(contract='native-agent-handoff-policy.v1',organization_id=c['organization_id'],
            agents=dict(codex=c['app_user_id'],jarvis=str(uuid.UUID(int=20))),issues=c['issues'])
        handoff_config=dict(contract='native-handoff-n8n-config.v1',policy=handoff_policy,credentials=dict(
            postgres=c['credentials']['postgres'],codex_oauth=dict(id=c['credentials']['codex_oauth'],type='oAuth2Api'),
            jarvis_oauth=dict(id='fixture-jarvis-oauth',type='oAuth2Api'),jarvis_header='fixture-jarvis-handoff',codex_header='fixture-codex-handoff'))
        hp=hm.render(handoff_config)
        package['workflows'].update({'handoff_'+key:value for key,value in hp['workflows'].items()})
        jarvis=hm.local('n8n_jarvis_admission');legacy=jarvis_fixture(handoff_config)
        package['workflows']['jarvis_admission']=jarvis.render(legacy,hashlib.sha256(jarvis.encoded(legacy)).hexdigest(),handoff_config)['workflow']
        package['workflows']['jarvis_context']=hm.local('n8n_hermes_context').render(handoff_config)
        package['workflows']['jarvis_checkpoint']=hm.local('n8n_hermes_context').checkpoint(handoff_config)
        history=hm.local('handoff_history');pin=c['issues'][str(uuid.UUID(int=4))]
        history_context=dict(project_id=pin['project_id'],architecture=dict(document_id='doc_'+'3'*32,
            version=pin['architecture_version'],markdown_sha256=pin['architecture_sha256']),
            work=dict(work_item_id=pin['work_id'],work_revision_sha256=pin['work_revision_sha256'],assignment_sha256='a'*64))
        history_selected=dict(contract='native-handoff-history-source.v1',policy=handoff_policy,scope=dict(kind='repository',id='jarvis'),
            contexts={str(uuid.UUID(int=4)):[dict(binding=pin,context=history_context)]})
        package['workflows']['handoff_history']=hm.local('n8n_handoff_history').render(history_selected,c['credentials']['postgres'],'fixture-handoff-history')
        native_history_selected=dict(history_selected,contract='hermes-runtime-history-source.v1')
        package['workflows']['hermes_history']=hm.local('n8n_hermes_history').render(native_history_selected,c['credentials']['postgres'],'fixture-handoff-history')
        sql("INSERT INTO linear_bridge.codex_apps VALUES('"+c['organization_id']+"','"+c['app_user_id']+"');")
        creds=[dict(id=c['credentials']['postgres'],name='Fixture SQL',type='postgres',data=dict(host='127.0.0.1',port=5432,database='postgres',user='codex_transport',password='synthetic',ssl='disable')),
            dict(id=c['credentials']['edge_header'],name='Fixture edge',type='httpHeaderAuth',data=dict(name='X-RRAS-Codex-Bridge',value='synthetic-edge-bridge')),
            dict(id=c['credentials']['runtime_header'],name='Fixture runtime',type='httpHeaderAuth',data=dict(name='Authorization',value='Bearer synthetic-runtime-bridge')),
            dict(id=c['credentials']['codex_oauth'],name='Fixture OAuth',type='oAuth2Api',data=dict(grantType='authorizationCode',authUrl='http://127.0.0.1:8899/authorize',accessTokenUrl='http://127.0.0.1:8899/token',clientId=c['oauth_client_id'],clientSecret='synthetic',scope='read write app:mentionable app:assignable',authentication='body',oauthTokenData=dict(access_token='synthetic-oauth-token',token_type='Bearer',expires_in=86400)))]
        jarvis_credential=json.loads(json.dumps(creds[-1]));jarvis_credential.update(id='fixture-jarvis-oauth',name='Fixture Jarvis OAuth')
        jarvis_credential['data']['oauthTokenData']['access_token']='synthetic-jarvis-oauth-token';creds.append(jarvis_credential)
        for role in ('jarvis','codex'):creds.append(dict(id='fixture-'+role+'-handoff',name='Fixture '+role+' handoff',type='httpHeaderAuth',
            data=dict(name='Authorization',value='Bearer synthetic-handoff-'+role)))
        creds.append(dict(id='fixture-handoff-history',name='Fixture selected handoff reader',type='httpHeaderAuth',data=dict(
            name='Authorization',value='Bearer synthetic-handoff-history')))
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
            # Exercise production's no-retention setting on the read-only reader.
            if name=='handoff_history':
                w['settings'].update(saveDataErrorExecution='none',saveDataSuccessExecution='none',saveExecutionProgress=False)
            for n in w['nodes']:
                if n['type']=='n8n-nodes-base.scheduleTrigger':
                    n['type']='n8n-nodes-base.manualTrigger';n['typeVersion']=1;n['parameters']={}
                if n['type']=='n8n-nodes-base.httpRequest' and n['parameters']['url']=='https://api.linear.app/graphql':
                    n['parameters']['url']='http://127.0.0.1:8899/graphql'
                if n['type']=='n8n-nodes-base.httpRequest' and n['parameters']['url']=='http://hermes:8642/v1/runs':
                    n['parameters']['url']='http://127.0.0.1:8899/hermes/v1/runs'
                for ref in n.get('credentials',{}).values():ref['id']=credential_refs[ref['id']]
            print('Importing fixture '+name,flush=True)
            workflows[name]=api('/rest/workflows',w)
        remote=r"""const http=require('node:http');const state={calls:[],activities:[],requests:[],interrupts:[],comments:{},sessions:{},sessionMutations:0,commentMutations:0,active:null,complete:false,uncertain:false,losePublication:false,wrongActor:false};
const uid=n=>'00000000-0000-0000-0000-'+n.toString(16).padStart(12,'0');
http.createServer(async(req,res)=>{let raw='';for await(const x of req)raw+=x;let b=raw?JSON.parse(raw):{};
state.requests.push({url:req.url,authorization:req.headers.authorization,query:b.query});
const reply=(status,v)=>{res.writeHead(status,{'Content-Type':'application/json'});res.end(JSON.stringify(v));};
if(req.url==='/fixture/status')return reply(200,state);
if(req.url==='/fixture/complete'){state.complete=true;return reply(200,{ok:true});}
if(req.url==='/fixture/uncertain'){state.uncertain=true;return reply(200,{ok:true});}
if(req.url==='/fixture/lose-publication'){state.losePublication=true;return reply(200,{ok:true});}
if(req.url==='/fixture/wrong-actor'){state.wrongActor=true;return reply(200,{ok:true});}
if(req.url==='/fixture/clear-wrong-actor'){state.wrongActor=false;return reply(200,{ok:true});}
if(req.url==='/fixture/deny-execution'){state.denyExecution=true;return reply(200,{ok:true});}
if(req.url==='/fixture/lose-handoff-comment'){state.loseHandoffComment=true;return reply(200,{ok:true});}
if(req.url==='/fixture/lose-handoff-session'){state.loseHandoffSession=true;return reply(200,{ok:true});}
if(req.url==='/hermes/v1/runs'){state.hermes=state.hermes||[];state.hermes.push(b);return reply(202,{run_id:'run_'+state.hermes.length.toString(16).padStart(32,'0')});}
if(req.url==='/graphql'){
const actor=req.headers.authorization==='Bearer synthetic-oauth-token'?uid(2):req.headers.authorization==='Bearer synthetic-jarvis-oauth-token'?uid(20):null;
if(!actor)return reply(403,{error:'fixture OAuth denied'});
const viewer={id:state.wrongActor?uid(20):actor,organization:{id:uid(1)}};
if(b.query.startsWith('mutation NativeHandoffComment')){const input=b.variables.input;state.commentMutations++;
 state.comments[input.id]={id:input.id,body:input.body,user:{id:actor,app:true},issue:{id:input.issueId},agentSessions:{nodes:[],pageInfo:{hasNextPage:false,endCursor:null}}};
 if(state.loseHandoffComment){state.loseHandoffComment=false;return res.destroy();}
 return reply(200,{data:{commentCreate:{success:true,comment:{id:input.id}}}});}
if(b.query.startsWith('mutation NativeHandoffSession')){const comment=state.comments[b.variables.input.commentId];if(!comment)return reply(200,{errors:[{message:'Comment not found'}]});
 state.sessionMutations++;const session={id:uid(600+state.sessionMutations),appUser:{id:actor},issue:comment.issue,creator:null,comment:{id:comment.id,user:comment.user},sourceComment:null};
 state.sessions[session.id]=session;comment.agentSessions.nodes.push({id:session.id,appUser:session.appUser,issue:session.issue});
 if(state.loseHandoffSession){state.loseHandoffSession=false;return res.destroy();}
 return reply(200,{data:{agentSessionCreateOnComment:{success:true,agentSession:{id:session.id}}}});}
if(b.query.startsWith('query NativeHandoffReadComment'))return reply(200,{data:{viewer,comment:state.comments[b.variables.id]||null}});
if(b.query.startsWith('query CodexNativeOrigin'))return reply(200,{data:{viewer:{id:uid(state.wrongActor?20:2),organization:{id:uid(1)}},
 sourceActor:{id:b.variables.actor,app:[uid(2),uid(20)].includes(b.variables.actor)},agentSession:state.sessions[b.variables.id]||{id:b.variables.id,appUser:{id:uid(2)},issue:{id:uid(4)},creator:{id:uid(6),app:false},comment:null,sourceComment:null}}});
if(b.query.startsWith('query JarvisNativeOrigin'))return reply(200,{data:{viewer,
 sourceActor:{id:b.variables.actor,app:[uid(2),uid(20)].includes(b.variables.actor)},agentSession:state.sessions[b.variables.id]||{id:b.variables.id,appUser:{id:uid(20)},issue:{id:uid(4)},creator:{id:uid(6),app:false},comment:null,sourceComment:null}}});
if(b.query.startsWith('query '))return reply(200,{data:{viewer}});
state.activities.push(b.variables.input);if(state.losePublication){state.losePublication=false;return res.destroy();}
return reply(200,{data:{agentActivityCreate:{success:true,agentActivity:{id:b.variables.input.id}}}});}
if(req.headers.authorization!=='Bearer synthetic-runtime-bridge')return reply(403,{error:'fixture runtime denied'});
if(req.url==='/runtime/v1/dispatch'){if(state.denyExecution)return reply(403,{contract:'codex-admission-refusal.v1',dispatch:b.dispatch_id,state:'failed',reason:'execution_not_authorized'});state.calls.push(b);state.active=b.dispatch_id;state.complete=false;state.uncertain=false;return reply(202,{dispatch:b.dispatch_id,state:'running',thread:'fixture-thread',turn:'fixture-turn'});}
if(req.url==='/runtime/v1/interrupt'){state.interrupts.push(b.dispatch_id);return reply(200,{dispatch:b.dispatch_id,state:'interrupted'});}
if(req.url.startsWith('/runtime/v1/runs/')){const id=req.url.split('/').pop();return reply(200,{dispatch:id,state:state.interrupts.includes(id)?'interrupted':state.complete?'completed':state.uncertain?'uncertain':'running',result:'Synthetic final result',thread:'fixture-thread',turn:'fixture-turn'});}
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
            result=api('/rest/workflows/'+ids[which]+'/run',dict(triggerToStartFrom=dict(name='Poll explicit handoffs' if which.startswith('handoff_') else 'Poll Codex transport')))
            assert 'executionId' in result,result
            for _ in range(100):
                status=sql("SELECT status FROM execution_entity WHERE id="+str(int(result['executionId']))+";").strip()
                if status not in ('','new','running','waiting'):break
                time.sleep(.25)
            assert status=='success', 'Engine execution failed: '+which+' '+status+' '+sql('SELECT left(data,14000) FROM execution_data ORDER BY \"executionId\" DESC LIMIT 1;')+' '+repr(request('/fixture/status',port=8899))
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
        request('/fixture/clear-wrong-actor',{},port=8899)
        uid=lambda number:str(uuid.UUID(int=number));handoff=hm.local('native_handoff')
        def lit(value):return "'"+value.replace("'","''")+"'"
        def js(value):return lit(json.dumps(value))+'::jsonb'
        sql("INSERT INTO linear_bridge.native_handoff_apps VALUES('"+uid(1)+"','codex','"+uid(2)+"'),('"+uid(1)+"','jarvis','"+uid(20)+"');"
            "INSERT INTO linear_bridge.native_handoff_issues VALUES('"+uid(1)+"','"+uid(4)+"',"+js(c['issues'][uid(4)])+");"
            "INSERT INTO linear_bridge.agent_sessions VALUES('"+uid(75)+"','"+uid(1)+"','"+uid(4)+"','fixture-hermes-75','fixture-run-75');"
            "INSERT INTO linear_bridge.hermes_runs VALUES('fixture-run-75','"+uid(75)+"','running',NULL,NULL);")
        for role in ('jarvis','codex'):
            w=workflows['handoff_'+role+'_request'];api('/rest/workflows/'+ids['handoff_'+role+'_request']+'/activate',dict(versionId=w['versionId']))
        for _ in range(30):
            response=request('/webhook/rras-native-handoff-jarvis',{},dict(Authorization='wrong'))
            if response['status']!=404:break
            time.sleep(.25)
        assert response['status']==403,response
        trusted=dict(session_id=uid(75),issue_id=uid(4),binding=c['issues'][uid(4)],parent_handoff_id=None,depth=0)
        arguments=dict(key='fixture-jarvis-to-codex',summary='A selected failure needs engineering investigation.',
            requested_action='Investigate, validate and report through the same work item.',references=[],limitations=['Synthetic fixture, no model.'])
        first_handoff=handoff.prepare(handoff_policy,'jarvis',trusted,arguments)
        def submit_handoff(intent):
            response=request('/webhook/rras-native-handoff-'+intent['sender'],intent,
                dict(Authorization='Bearer synthetic-handoff-'+intent['sender']))
            assert response['status']==200,response
            assert json.loads(response['body'])['request_id']==intent['id'],response
        submit_handoff(first_handoff);submit_handoff(first_handoff)
        execute('handoff_jarvis_comment')
        assert json.loads(request('/fixture/status',port=8899)['body'])['commentMutations']==0
        sql("UPDATE linear_bridge.hermes_runs SET status='completed',completed_at=now() WHERE hermes_run_id='fixture-run-75';")
        request('/fixture/lose-handoff-comment',{},port=8899);execute('handoff_jarvis_comment');execute('handoff_jarvis_comment')
        native_status=json.loads(request('/fixture/status',port=8899)['body'])
        assert native_status['commentMutations']==1,dict(mutations=native_status['commentMutations'],requests=native_status['requests'][-8:],
            database=sql('SELECT id,comment_state,session_state,source_quiescence FROM linear_bridge.native_handoffs;'),
            engine=sql('SELECT left(data,12000) FROM execution_data ORDER BY \"executionId\" DESC LIMIT 1;'))
        execute('handoff_jarvis_reconcile')
        assert sql("SELECT comment_state||':'||session_state FROM linear_bridge.native_handoffs WHERE id='"+first_handoff['id']+"';").strip()=='confirmed:pending'
        request('/fixture/lose-handoff-session',{},port=8899);execute('handoff_jarvis_session');execute('handoff_jarvis_session')
        execute('handoff_jarvis_reconcile')
        target=sql("SELECT target_session_id FROM linear_bridge.native_handoffs WHERE id='"+first_handoff['id']+"';").strip()
        assert target==uid(601)
        status=json.loads(request('/fixture/status',port=8899)['body']);assert status['sessionMutations']==1
        native=dict(body,appUserId=uid(2),webhookTimestamp=int(time.time()*1000),agentSession=dict(id=target,issueId=uid(4),
            appUserId=uid(2),commentId=first_handoff['comment_id'],creatorId=None),promptContext=handoff.comment_body(first_handoff))
        hs=dict(headers);hs['Linear-Delivery']=uid(650);hs['X-RRAS-Codex-Body-Sha256']=hashlib.sha256(json.dumps(native).encode()).hexdigest()
        response=request(path,native,hs);assert response['status']==200,response
        assert request(path,native,hs)['status']==200
        execute('dispatch');execute('handoff_jarvis_reconcile')
        assert sql("SELECT state FROM linear_bridge.native_handoffs WHERE id='"+first_handoff['id']+"';").strip()=='acknowledged'
        status=json.loads(request('/fixture/status',port=8899)['body']);assert len(status['calls'])==4
        assert status['calls'][-1]['session_id']==target and status['calls'][-1]['binding']==trusted['binding']
        assert status['calls'][-1]['incoming_handoff']==dict(id=first_handoff['id'],depth=1,source_session_id=trusted['session_id'],
            sender_app_user_id=uid(20),recipient_app_user_id=uid(2),target_session_id=target)
        request('/fixture/complete',{},port=8899);execute('reconcile');execute('handoff_jarvis_reconcile')
        assert sql("SELECT state FROM linear_bridge.native_handoffs WHERE id='"+first_handoff['id']+"';").strip()=='completed'
        # Human follow-up in the same native session keeps its incoming chain;
        # an ordinary prompt must not reset a later return handoff's depth.
        deliver(601,651,652);execute('dispatch')
        followup=json.loads(request('/fixture/status',port=8899)['body'])['calls'][-1]
        assert followup['incoming_handoff']['id']==first_handoff['id'] and followup['incoming_handoff']['depth']==1
        request('/fixture/complete',{},port=8899);execute('reconcile')
        second_handoff=handoff.prepare(handoff_policy,'codex',dict(trusted,session_id=target,parent_handoff_id=first_handoff['id'],depth=1),
            dict(arguments,key='fixture-codex-to-jarvis',requested_action='Review the engineering result and report remaining questions.'))
        submit_handoff(second_handoff);execute('handoff_codex_comment');execute('handoff_codex_reconcile')
        execute('handoff_codex_session');execute('handoff_codex_reconcile')
        jarvis_target=sql("SELECT target_session_id FROM linear_bridge.native_handoffs WHERE id='"+second_handoff['id']+"';").strip()
        assert jarvis_target==uid(602)
        status=json.loads(request('/fixture/status',port=8899)['body'])
        assert status['comments'][first_handoff['comment_id']]['user']['id']==uid(20)
        assert status['sessions'][target]['appUser']['id']==uid(2)
        assert status['comments'][second_handoff['comment_id']]['user']['id']==uid(2)
        assert status['sessions'][jarvis_target]['appUser']['id']==uid(20)
        assert status['commentMutations']==2 and status['sessionMutations']==2
        # The patched legacy-shaped workflow runs in the actual engine; its
        # Hermes endpoint is synthetic and starts no model or real session.
        api('/rest/workflows/'+ids['jarvis_admission']+'/activate',dict(versionId=workflows['jarvis_admission']['versionId']))
        def jarvis_deliver(value,check):
            for _ in range(30):
                response=request('/webhook/fixture-jarvis-inbound',value,dict(Authorization='Bearer synthetic-handoff-jarvis'))
                if response['status']!=404:break
                time.sleep(.25)
            assert response['status']==200,response
            for _ in range(80):
                if check():return
                time.sleep(.25)
            raise ValueError('Patched Jarvis fixture did not reach expected state: '+sql('SELECT left(data,12000) FROM execution_data ORDER BY "executionId" DESC LIMIT 1;'))
        jarvis_event=dict(type='AgentSessionEvent',action='created',organizationId=uid(1),deliveryId=uid(700),
            agentSession=dict(id=jarvis_target,issueId=uid(4),commentId=second_handoff['comment_id']),promptContext='Synthetic assistant handoff.')
        jarvis_deliver(jarvis_event,lambda:sql("SELECT count(*) FROM linear_bridge.jarvis_engineering_runs WHERE session_id='"+jarvis_target+"';").strip()=='1')
        state=json.loads(request('/fixture/status',port=8899)['body']);assert len(state['hermes'])==1
        assert 'run terminal commands' in state['hermes'][0]['instructions'] and 'Engineering context is explicit' in state['hermes'][0]['instructions']
        for key in ('jarvis_context','jarvis_checkpoint'):
            api('/rest/workflows/'+ids[key]+'/activate',dict(versionId=workflows[key]['versionId']))
        actual_native=dict(organization_id=uid(1),session_id=jarvis_target,hermes_session_id='linear:'+uid(1)+':'+jarvis_target,run_id='run_'+'0'*31+'1')
        context_path='/webhook/rras-jarvis-engineering-context';native_headers=dict(Authorization='Bearer synthetic-handoff-jarvis')
        for _ in range(30):
            response=request(context_path,dict(contract='jarvis-native-context.v1',**actual_native),native_headers)
            if response['status']!=404:break
            time.sleep(.25)
        assert response['status']==200,response
        actual_context=json.loads(response['body'])['context']
        assert actual_context==dict(session_id=jarvis_target,issue_id=uid(4),binding=pin,parent_handoff_id=second_handoff['id'],depth=2,delivery_id=uid(700))
        wrong_native=dict(actual_native,session_id=uid(999),hermes_session_id='linear:'+uid(1)+':'+uid(999))
        response=request(context_path,dict(contract='jarvis-native-context.v1',**wrong_native),native_headers)
        assert response['status']==200 and json.loads(response['body'])['context'] is None
        with tempfile.TemporaryDirectory(prefix='shrr-hermes-tool-fixture-') as folder:
            hermes_adapter=hm.local('hermes_runtime');native_queue=hm.local('runtime_handoff').Queue(Path(folder)/'queue',create=True)
            def native_call(kind,value):
                endpoint=context_path if kind=='context' else '/webhook/rras-jarvis-engineering-checkpoint'
                response=request(endpoint,value,native_headers);assert response['status']==200,response
                if not response['body']:
                    flat=json.loads(sql('SELECT data FROM execution_data ORDER BY "executionId" DESC LIMIT 1;'))
                    ref=lambda value:flat[int(value)] if type(value) is str and value.isdecimal() else value
                    error=ref(ref(flat[0]['resultData']).get('error',{}))
                    raise ValueError('Native '+kind+' workflow failed: '+str(ref(error.get('message','unconfirmed'))))
                return json.loads(response['body'])
            adapter=hermes_adapter.Adapter(dict(contract='hermes-native-reporting.v1',policy=handoff_policy,
                scope=dict(kind='repository',id='jarvis'),contexts={uid(4):history_context},queue=str(native_queue.path),origin='http://fixture.invalid',
                token_file='/not-opened-in-synthetic-fixture'),actual=lambda:actual_native,call=native_call)
            adapter.record('checkpoint',dict(key='actual-n8n-native-tool',observations=['Native Jarvis report retained under the actual run.'],next_step='Deliver through the scoped owned-history importer.'))
            delivered=adapter.flush()
            if delivered['pending']:
                with native_queue.connection() as db:frame=native_queue.i.local('contract').decode(db.execute('SELECT intent FROM handoffs').fetchone()[0])
                try:adapter.deliver(frame)
                except Exception as error:raise ValueError('Native checkpoint fixture delivery refused: '+type(error).__name__+': '+str(error)[:2000]) from None
                raise ValueError('Native checkpoint acknowledgment was not retained')
            assert adapter.flush()['delivered']==0
            assert sql('SELECT count(*) FROM linear_bridge.jarvis_engineering_checkpoints;').strip()=='1'
        echo=dict(jarvis_event,action='prompted',deliveryId=uid(701),agentActivity=dict(userId=uid(20)))
        jarvis_deliver(echo,lambda:sql("SELECT count(*) FROM linear_bridge.jarvis_engineering_admissions WHERE delivery_id='"+uid(701)+"' AND NOT permitted;").strip()=='1')
        assert len(json.loads(request('/fixture/status',port=8899)['body'])['hermes'])==1
        unselected=dict(jarvis_event,deliveryId=uid(702),agentSession=dict(id=uid(703),issue=dict(id=uid(99))))
        jarvis_deliver(unselected,lambda:sql("SELECT count(*) FROM linear_bridge.hermes_runs WHERE agent_session_id='"+uid(703)+"';").strip()=='1')
        state=json.loads(request('/fixture/status',port=8899)['body']);assert len(state['hermes'])==2
        assert 'Engineering context is explicit' not in state['hermes'][1]['instructions']
        execute('handoff_codex_reconcile')
        assert sql("SELECT state FROM linear_bridge.native_handoffs WHERE id='"+second_handoff['id']+"';").strip()=='acknowledged'
        sql("UPDATE linear_bridge.hermes_runs SET status='completed',completed_at=now() WHERE agent_session_id='"+jarvis_target+"';")
        execute('handoff_codex_reconcile')
        assert sql("SELECT state FROM linear_bridge.native_handoffs WHERE id='"+second_handoff['id']+"';").strip()=='completed'
        other_pin=dict(pin,project_id='prj_'+'9'*32,work_id='wrk_'+'8'*32)
        other_policy=dict(handoff_policy,issues={uid(99):other_pin})
        other_intent=handoff.prepare(other_policy,'jarvis',dict(trusted,session_id=uid(76),issue_id=uid(99),binding=other_pin),
            dict(arguments,key='foreign-project-fixture',summary='UNSELECTED-PROJECT-NARRATIVE'))
        sql("INSERT INTO linear_bridge.native_handoff_issues VALUES('"+uid(1)+"','"+uid(99)+"',"+js(other_pin)+");"
            "INSERT INTO linear_bridge.agent_sessions VALUES('"+uid(76)+"','"+uid(1)+"','"+uid(99)+"','fixture-foreign-session','fixture-foreign-run');"
            "SELECT linear_bridge.native_handoff_request('"+uid(1)+"','jarvis',"+js(other_intent)+','+lit(handoff.comment_body(other_intent))+');')
        api('/rest/workflows/'+ids['handoff_history']+'/activate',dict(versionId=workflows['handoff_history']['versionId']))
        history_path='/webhook/rras-native-handoff-events-'+pin['project_id']
        for _ in range(30):
            response=request(history_path,dict(after=0),dict(Authorization='wrong'))
            if response['status']!=404:break
            time.sleep(.25)
        assert response['status']==403,response
        def query_history(after):
            response=request(history_path,dict(after=after),dict(Authorization='Bearer synthetic-handoff-history'))
            assert response['status']==200,response
            assert 'UNSELECTED-PROJECT-NARRATIVE' not in response['body']
            return json.loads(response['body'])
        query_history(0)
        time.sleep(3)
        no_retention_running=sql("SELECT count(*) FROM execution_entity WHERE status='running' AND \"deletedAt\" IS NOT NULL AND \"workflowId\"='"+ids['handoff_history']+"';").strip()
        assert int(no_retention_running)>=1, 'Expected soft-deleted running execution in no-retention fixture'
        print(json.dumps(dict(fixture_soft_deleted_running_records=int(no_retention_running),fixture_reader_responded=True)),flush=True)
        with tempfile.TemporaryDirectory(prefix='shrr-handoff-history-fixture-') as folder:
            spool=hm.local('capture_intake').Spool(Path(folder)/'spool',create=True)
            observed=history.poll(spool,history_selected,query_history)
            assert observed['events_staged']==6 and observed['after']==6
            assert history.poll(spool,history_selected,query_history)['events_staged']==0
            with spool.connection() as db:records=[spool.c.decode(x[0]) for x in db.execute("SELECT request FROM items WHERE kind='native_handoff' ORDER BY sequence")]
            assert [r['body']['state'] for r in records]==['requested','acknowledged','completed']*2
            assert all(r['context']==history_context and r['source']['kind']=='imported' for r in records)
        api('/rest/workflows/'+ids['hermes_history']+'/activate',dict(versionId=workflows['hermes_history']['versionId']))
        native_history_path='/webhook/rras-hermes-engineering-history-'+pin['project_id']
        for _ in range(30):
            response=request(native_history_path,dict(after_admission=0,after_run=0,after_checkpoint=0),native_headers)
            if response['status']!=404:break
            time.sleep(.25)
        assert response['status']==403,response
        def native_history_query(cursor):
            response=request(native_history_path,cursor,dict(Authorization='Bearer synthetic-handoff-history'))
            assert response['status']==200,response
            return json.loads(response['body'])
        with tempfile.TemporaryDirectory(prefix='shrr-native-history-fixture-') as folder:
            native_spool=hm.local('capture_intake').Spool(Path(folder)/'spool',create=True)
            native_source=hm.local('hermes_history');result=native_source.poll(native_spool,native_history_selected,native_history_query)
            assert result==dict(admissions=1,runs=1,checkpoints=1,models_started=0),result
            with native_spool.connection() as db:
                native_records=[native_spool.c.decode(row[0]) for row in db.execute('SELECT request FROM items')]
                count=db.execute('SELECT count(*) FROM items').fetchone()[0]
            assert [row['body']['phase'] for row in native_records if row['operation']=='attempt.record']==['started','completed']
            assert sum(row['operation']=='checkpoint.report' for row in native_records)==1
            assert all(row['context']==history_context for row in native_records)
            native_source.poll(native_spool,native_history_selected,native_history_query)
            with native_spool.connection() as db:assert db.execute('SELECT count(*) FROM items').fetchone()[0]==count
        request('/fixture/deny-execution',{},port=8899)
        before=len(json.loads(request('/fixture/status',port=8899)['body'])['calls'])
        denied=deliver(800,801);execute('dispatch')
        assert sql("SELECT state FROM linear_bridge.codex_events WHERE id='"+denied+"';").strip()=='failed'
        assert len(json.loads(request('/fixture/status',port=8899)['body'])['calls'])==before
        assert 'No model turn was started' in sql("SELECT content->>'body' FROM linear_bridge.codex_outbox WHERE source_key='result:"+denied+":failed';")
        print(json.dumps(dict(n8n_version='2.28.3',actual_import=True,actual_http_webhook=True,header_denial=True,durable_receipt=True,duplicate_receipt=True,initial_activity=True,exact_single_dispatch=True,runtime_reconcile=True,uncertain_then_final=True,follow_up_serialized=True,matching_turn_stop=True,one_cancellation_result=True,lost_publication_no_resend=True,wrong_oauth_actor_refused=True,final_activity=True,role_grants=True,jarvis_sentinel_preserved=True,
            handoff_private_intake=True,handoff_actual_engine_both_publish_directions=True,handoff_source_quiescence=True,handoff_lost_comment_and_session_response_reconciled=True,
            handoff_separate_oauth_actors=True,handoff_correlated_codex_dispatch_once=True,handoff_ack_and_terminal=True,
            handoff_history_read_only_endpoint=True,handoff_history_scope_denial=True,handoff_history_exact_typed_projection=True,pre_dispatch_execution_refusal=True,
            jarvis_admission_actual_engine=True,jarvis_correlated_handoff_admitted=True,jarvis_agent_echo_denied=True,jarvis_unselected_run_preserved=True,
            jarvis_exact_native_run_context=True,jarvis_wrong_native_run_context_denied=True,jarvis_scoped_checkpoint_intake=True,
            jarvis_private_history_reader=True,jarvis_producer_private_history_denied=True,jarvis_typed_history_projection=True,
            hermes_execution='synthetic_http_endpoint_only',
            network='isolated container namespace',production_mounts=False,real_credentials=False,paid_model_calls=0)))
    finally:
        for name in reversed(created):
            subprocess.run(['docker','rm','-f',name],capture_output=True,timeout=30)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--isolated-containers',action='store_true',required=True)
    parser.parse_args();probe()
