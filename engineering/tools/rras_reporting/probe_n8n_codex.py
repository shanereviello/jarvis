"""Opt-in model-free transport acceptance in disposable network-isolated containers."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import time
import uuid

ROOT=Path(__file__).resolve().parents[2]


def run(argv,data=None):
    p=subprocess.run(argv,input=data,capture_output=True,text=True,timeout=40)
    if p.returncode:raise ValueError('isolated fixture failed: '+p.stderr[-1500:])
    return p.stdout


def fixture():
    uid=lambda n:str(uuid.UUID(int=n))
    return dict(contract='codex-n8n-config.v1',organization_id=uid(1),app_user_id=uid(2),
        oauth_client_id=uid(3),agent_actor_ids=[uid(2),uid(20)],
        issues={uid(4):dict(project_id='prj_'+'1'*32,work_id='wrk_'+'2'*32,plan_id='SHRR-03',
            work_revision_sha256='3'*64,architecture_version=4,architecture_sha256='4'*64)},
        n8n_redirect_url='https://n8n.example.com/rest/oauth2-credential/callback',
        verified_webhook_url='https://agents.example.com/webhooks/codex',runtime_origin='http://codex-runtime:8766',
        credentials=dict(postgres='fixture-pg',edge_header='fixture-edge',runtime_header='fixture-runtime',
                         codex_oauth='fixture-oauth'))


JAVASCRIPT=r"""
const assert=require('node:assert/strict'),fs=require('node:fs');
const input=JSON.parse(fs.readFileSync(0,'utf8')), policy=input.policy;
const admit=new Function(input.admission+'\nreturn admit;')();
const uid=n=>'00000000-0000-0000-0000-'+String(n).padStart(12,'0');
const now=Date.now(),body={type:'AgentSessionEvent',action:'created',organizationId:policy.organization_id,
 webhookTimestamp:now,agentSession:{id:uid(5),issue:{id:uid(4)},creatorId:uid(6)},promptContext:'Synthetic mention/delegation'};
const headers={'x-rras-codex-verified':'v1','linear-delivery':uid(7),'x-rras-codex-body-sha256':'a'.repeat(64)};
assert.equal(admit({headers,body},policy,now).envelope.binding.plan_id,'SHRR-03');
const follow=structuredClone(body);follow.action='prompted';
follow.agentActivity={id:uid(8),agentSessionId:uid(5),content:{type:'prompt',body:'Follow-up'},userId:uid(6)};
assert.equal(admit({headers,body:follow},policy,now).envelope.message,'Follow-up');
const stop=structuredClone(follow);stop.agentActivity.signal='stop';delete stop.agentActivity.content.body;
assert.equal(admit({headers,body:stop},policy,now).envelope.signal,'stop');
for(const mutate of [
 x=>x.body.organizationId=uid(99),x=>x.body.appUserId=uid(99),x=>x.body.oauthClientId=uid(99),
 x=>x.body.webhookTimestamp=0,x=>x.body.agentSession.issue.id=uid(99),
 x=>x.headers['x-rras-codex-verified']='spoof',x=>x.headers['x-rras-codex-body-sha256']='invalid',
 x=>x.body.agentSession.issueId=uid(99),x=>x.body.agentSession.creatorId=policy.app_user_id]){
 const x=structuredClone({headers,body});mutate(x);assert.throws(()=>admit(x,policy,now));
}
for(const w of Object.values(input.package.workflows))for(const n of w.nodes){
 if(n.type.endsWith('.code'))new Function('$input','$',n.parameters.jsCode);
 if(n.type.endsWith('.postgres')&&n.parameters.options.queryReplacement)
  new Function('$json','return '+n.parameters.options.queryReplacement.slice(3,-2));
}
const check=input.package.workflows.outbound.nodes.find(n=>n.name==='Verify Codex actor').parameters.jsCode;
const verified=new Function('$input','$',check), source=()=>({first:()=>({json:{id:uid(9)}})});
const viewer=id=>({first:()=>({json:{statusCode:200,body:{data:{viewer:{id,organization:{id:policy.organization_id}}}}}})});
assert.equal(verified(viewer(policy.app_user_id),source)[0].json.permitted,true);
assert.equal(verified(viewer(uid(20)),source)[0].json.permitted,false);
(async()=>{
 const worker=(await import('data:text/javascript;base64,'+Buffer.from(input.worker).toString('base64'))).default;
 const env={CODEX_WEBHOOK_SECRET:'synthetic-webhook-secret-at-least-24',CODEX_N8N_BRIDGE_SECRET:'synthetic-bridge-secret-at-least-32',
 CODEX_N8N_URL:'https://n8n.example.com/webhook/rras-codex-agent-events',CODEX_ORGANIZATION_ID:policy.organization_id,
 CF_ACCESS_CLIENT_ID:'synthetic-access-client-id',CF_ACCESS_CLIENT_SECRET:'synthetic-access-client-secret'};
 const key=await crypto.subtle.importKey('raw',new TextEncoder().encode(env.CODEX_WEBHOOK_SECRET),
   {name:'HMAC',hash:'SHA-256'},false,['sign']);
 const raw=JSON.stringify(body),bytes=new TextEncoder().encode(raw);
 const sig=Buffer.from(await crypto.subtle.sign('HMAC',key,bytes)).toString('hex');
 let forwards=0;
 global.fetch=async(url,options)=>{
  forwards++;assert.equal(url,env.CODEX_N8N_URL);
  assert.equal(options.headers.get('X-RRAS-Codex-Bridge'),env.CODEX_N8N_BRIDGE_SECRET);
  assert.equal(options.headers.get('CF-Access-Client-Id'),env.CF_ACCESS_CLIENT_ID);
  assert.equal(options.headers.get('CF-Access-Client-Secret'),env.CF_ACCESS_CLIENT_SECRET);
  assert.equal(new TextDecoder().decode(options.body),raw);
  assert.equal(options.redirect,'error');return new Response('ok',{status:200});
 };
 const request=(text=raw,signature=sig)=>new Request('https://agents.example.com/webhooks/codex',
  {method:'POST',headers:{'linear-delivery':uid(7),'linear-signature':signature},body:text});
 assert.equal((await worker.fetch(request(),env)).status,200);assert.equal(forwards,1);
 const missingAccess={...env};delete missingAccess.CF_ACCESS_CLIENT_SECRET;
 assert.equal((await worker.fetch(request(),missingAccess)).status,503);assert.equal(forwards,1);
 assert.equal((await worker.fetch(request(raw+' '),env)).status,403);
 assert.equal((await worker.fetch(request(raw,'0'.repeat(64)),env)).status,403);assert.equal(forwards,1);
 console.log(JSON.stringify({admission:true,follow_up:true,stop:true,scope_refusals:9,
   workflow_code_compiles:true,wrong_credential_refused:true,edge_hmac_forwarding:true,
   access_service_headers:true,missing_access_refused:true,models_started:0}));
})().catch(e=>{console.error(e);process.exitCode=1;});
"""


def probe():
    spec=importlib.util.spec_from_file_location('isolated_n8n',Path(__file__).with_name('n8n_codex.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    c=fixture();package=module.render(c)
    payload=dict(policy={k:c[k] for k in ['organization_id','app_user_id','oauth_client_id','agent_actor_ids','issues']},
        package=package,admission=Path(__file__).with_name('n8n_codex_admission.js').read_text(),
        worker=Path(__file__).with_name('codex_edge_worker.mjs').read_text())
    print(run(['docker','run','--rm','-i','--pull=never','--network','none','--read-only','--cap-drop','ALL',
        '--security-opt','no-new-privileges','--user','node','--entrypoint','node',
        'docker.n8n.io/n8nio/n8n:2.28.3','-e',JAVASCRIPT],json.dumps(payload)).strip(),flush=True)
    name='rras-codex-n8n-fixture-'+uuid.uuid4().hex[:12];started=False
    try:
        run(['docker','run','-d','--pull=never','--name',name,'--network','none','--read-only',
            '--cap-drop','ALL','--security-opt','no-new-privileges','--user','postgres',
            '--tmpfs','/tmp:rw,nosuid,size=256m,mode=1777',
            '--tmpfs','/var/run/postgresql:rw,nosuid,size=8m,mode=1777',
            '-e','PGDATA=/tmp/codex-fixture/pgdata','-e','POSTGRES_HOST_AUTH_METHOD=trust',
            'postgres:18','postgres','-c','listen_addresses='])
        started=True
        for _ in range(40):
            ready=subprocess.run(['docker','exec',name,'pg_isready','-U','postgres'],capture_output=True)
            if ready.returncode==0:break
            time.sleep(.25)
        else:raise ValueError('isolated PostgreSQL fixture did not start')
        def sql(text):return run(['docker','exec','-i',name,'psql','-X','-A','-t','-v','ON_ERROR_STOP=1','-U','postgres'],text)
        sql('CREATE SCHEMA linear_bridge;\n'+(ROOT/'contracts/linear-codex-n8n-v1.sql').read_text())
        org,app=c['organization_id'],c['app_user_id']
        sql("INSERT INTO linear_bridge.codex_apps VALUES('"+org+"','"+app+"');")
        event=dict(contract='codex-admitted-event.v1',organization_id=org,app_user_id=app,
            session_id=str(uuid.UUID(int=5)),issue_id=str(uuid.UUID(int=4)),source_key='created:fixture',
            source_actor_id=str(uuid.UUID(int=6)),message='Synthetic fixture',signal=None,
            binding=c['issues'][str(uuid.UUID(int=4))],action='created')
        def accept(delivery,envelope=event,sha='a'*64):
            raw=json.dumps(envelope);assert '$fixture$' not in raw
            return ("SELECT inserted FROM linear_bridge.codex_accept('"+org+"','"+app+"','"+
                str(uuid.UUID(int=delivery))+"','"+sha+"',$fixture$"+raw+"$fixture$::jsonb);")
        assert sql(accept(7)).strip()=='t'
        assert sql(accept(7)).strip()=='f'
        assert sql(accept(8)).strip()=='f'
        try:sql(accept(9,dict(event,message='Changed content')))
        except ValueError:pass
        else:raise ValueError('changed source identity accepted')
        assert sql('SELECT count(*) FROM linear_bridge.codex_events;').strip()=='1'
        assert sql('SELECT count(*) FROM linear_bridge.codex_outbox;').strip()=='1'
        assert sql('SELECT count(*) FROM linear_bridge.codex_deliveries;').strip()=='2'
        for which in ['dispatch','reconcile','outbound']:
            for n in package['workflows'][which]['nodes']:
                if not n['type'].endswith('.postgres'):continue
                query=n['parameters']['query']
                if '$1' in query:
                    signature='uuid,text,text' if which=='outbound' else 'uuid,jsonb'
                    sql('PREPARE fixture_query('+signature+') AS '+query+';\nDEALLOCATE fixture_query;')
                else:sql('BEGIN;\n'+query+';\nROLLBACK;')
        second=dict(event,session_id=str(uuid.UUID(int=50)),source_key='created:second-fixture')
        sql(accept(51,second))
        first_id=sql("SELECT id FROM linear_bridge.codex_events WHERE source_key='created:fixture';").strip()
        second_id=sql("SELECT id FROM linear_bridge.codex_events WHERE source_key='created:second-fixture';").strip()
        sql("UPDATE linear_bridge.codex_events SET state='dispatching' WHERE id='"+first_id+"';")
        try:sql("UPDATE linear_bridge.codex_events SET state='dispatching' WHERE id='"+second_id+"';")
        except ValueError:pass
        else:raise ValueError('concurrent worktree dispatch accepted')
        assert sql("SELECT count(*) FROM linear_bridge.codex_events WHERE state='dispatching';").strip()=='1'
        print(json.dumps(dict(postgres_accept_replay=True,changed_source_refused=True,workspace_serialization=True,
            single_event_and_initial_reply=True,workflow_queries_prepared=True,
            production_databases_changed=False,fixture_container=name)),flush=True)
    finally:
        if started:run(['docker','rm','-f',name])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--isolated-containers',action='store_true',required=True)
    parser.parse_args();probe()
