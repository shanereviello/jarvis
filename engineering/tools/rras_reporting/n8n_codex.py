"""Render inactive Codex-only n8n workflows. No credential values or network writes."""
import argparse
import copy
import ipaddress
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
import uuid

ROOT=Path(__file__).resolve().parent
SCOPES=['read','write','app:mentionable','app:assignable']


def identifier(value):
    if not isinstance(value,str) or str(uuid.UUID(value))!=value:raise ValueError('canonical UUID required')
    return value


def url(value, public=True):
    p=urlsplit(value)
    if (p.username or p.password or p.query or p.fragment or not p.hostname or
            p.scheme not in (('https',) if public else ('http','https'))):
        raise ValueError('fixed credential-free endpoint required')
    if public:
        try:ipaddress.ip_address(p.hostname)
        except ValueError:pass
        else:raise ValueError('public DNS endpoint required')
    return value.rstrip('/')


def configuration(value):
    if type(value) is not dict or set(value)!={'contract','organization_id','app_user_id','oauth_client_id',
            'agent_actor_ids','issues','n8n_redirect_url','verified_webhook_url','runtime_origin','credentials'}:
        raise ValueError('exact Codex n8n binding required')
    if value['contract']!='codex-n8n-config.v1':raise ValueError('wrong contract')
    for key in ('organization_id','app_user_id'):identifier(value[key])
    # Linear OAuth client IDs can be 32 hexadecimal characters. They are not
    # actor UUIDs; retain their exact spelling for webhook comparisons.
    client=value['oauth_client_id']
    if not isinstance(client,str) or not re.fullmatch(
            r'(?:[0-9a-f]{32}|[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})',client):
        raise ValueError('Linear OAuth client ID required')
    if type(value['agent_actor_ids']) is not list or value['app_user_id'] not in value['agent_actor_ids']:
        raise ValueError('explicit agent echo exclusion required')
    for actor in value['agent_actor_ids']:identifier(actor)
    # Reuse shape validation without granting runtime authority or selecting a binary.
    import importlib.util
    spec=importlib.util.spec_from_file_location('n8n_runtime_policy',ROOT/'codex_runtime.py')
    runtime=importlib.util.module_from_spec(spec);spec.loader.exec_module(runtime)
    runtime.policy(dict(contract='codex-runtime-policy.v1',organization_id=value['organization_id'],
        app_user_id=value['app_user_id'],execution_authorized=False,
        execution_authority_reference='rendering only',binary='/usr/bin/false',cwd='/',
        sandbox='read-only',issues=value['issues']))
    url(value['n8n_redirect_url']);url(value['verified_webhook_url']);url(value['runtime_origin'],False)
    if urlsplit(value['verified_webhook_url']).path!='/webhooks/codex':
        raise ValueError('dedicated verified Codex path required')
    if set(value['credentials'])!={'postgres','edge_header','runtime_header','codex_oauth'}:
        raise ValueError('four explicit n8n credential references required')
    refs=list(value['credentials'].values())
    if any(not isinstance(x,str) or not x.strip() or len(x)>128 for x in refs) or len(set(refs))!=4:
        raise ValueError('distinct credential references required')
    return copy.deepcopy(value)


def render(value):
    c=configuration(value); org=c['organization_id'];app=c['app_user_id']
    select=f"organization_id='{org}'::uuid AND app_user_id='{app}'::uuid"
    policy={k:c[k] for k in ['organization_id','app_user_id','oauth_client_id','agent_actor_ids','issues']}
    credentials=c['credentials']
    def node(name,kind,parameters,credential=None):
        value=dict(id=str(uuid.uuid5(uuid.NAMESPACE_URL,'rras:v04:codex:'+name)),name=name,
            type='n8n-nodes-base.'+kind,typeVersion={'webhook':2.1,'respondToWebhook':1.4,
            'postgres':2.6,'httpRequest':4.2,'code':2,'scheduleTrigger':1.2,'if':2.2}[kind],
            position=[0,0],parameters=parameters)
        if credential:
            value['credentials']={credential[0]:dict(id=credentials[credential[1]],name='Codex '+credential[1])}
        return value
    def code(name,source):return node(name,'code',dict(jsCode=source,mode='runOnceForAllItems'))
    def pg(name,query,replacements=None):
        return node(name,'postgres',dict(operation='executeQuery',query=query,
            options={} if replacements is None else dict(queryReplacement=replacements)),('postgres','postgres'))
    def http(name,endpoint,body=None,oauth=False):
        p=dict(method='GET' if body is None else 'POST',url=endpoint,
            authentication='genericCredentialType',genericAuthType='oAuth2Api' if oauth else 'httpHeaderAuth',
            options=dict(timeout=15000,response=dict(response=dict(fullResponse=True,neverError=True))))
        if body is not None:p.update(sendBody=True,contentType='raw',rawContentType='application/json',body=body)
        result=node(name,'httpRequest',p,('oAuth2Api','codex_oauth') if oauth else ('httpHeaderAuth','runtime_header'))
        result.update(onError='continueRegularOutput',retryOnFail=False)
        return result
    def schedule():return node('Poll Codex transport','scheduleTrigger',dict(rule=dict(interval=[dict(field='seconds',secondsInterval=5)])))
    def workflow(name,nodes,connections=None):
        if connections is None:
            connections={a['name']:dict(main=[[dict(node=b['name'],type='main',index=0)]]) for a,b in zip(nodes,nodes[1:])}
        for i,n in enumerate(nodes):n['position']=[240*i,0]
        return dict(name=name,active=False,nodes=nodes,connections=connections,
            settings=dict(executionOrder='v1',saveDataErrorExecution='none',saveDataSuccessExecution='none',
                          saveManualExecutions=False,executionTimeout=60),
            tags=[],pinData={})

    admission=(ROOT/'n8n_codex_admission.js').read_text()
    inbound=workflow('Codex Inbound v0.4 (inactive)',[
        node('Codex verified webhook','webhook',dict(httpMethod='POST',path='rras-codex-agent-events',
            responseMode='responseNode',authentication='headerAuth',options={}),('httpHeaderAuth','edge_header')),
        code('Admit Codex event',admission+'\nconst policy='+json.dumps(policy)+';\nreturn [{json:admit($input.first().json,policy)}];'),
        pg('Retain Codex event',
            'SELECT * FROM linear_bridge.codex_accept($1::uuid,$2::uuid,$3::uuid,$4::text,$5::jsonb)',
            '={{ ['+json.dumps(org)+','+json.dumps(app)+',$json.delivery_id,$json.raw_body_sha256,JSON.stringify($json.envelope)] }}'),
        node('Acknowledge durable receipt','respondToWebhook',dict(respondWith='json',
            responseBody='={{ {accepted:true,event_id:$json.event_id,inserted:$json.inserted} }}',
            options=dict(responseCode=200)))])

    claim=f"""WITH candidate AS (
 SELECT e.id FROM linear_bridge.codex_events e WHERE {select.replace('organization_id','e.organization_id').replace('app_user_id','e.app_user_id')}
 AND e.state='pending' AND (e.envelope->>'signal'='stop' OR NOT EXISTS (
 SELECT 1 FROM linear_bridge.native_handoffs h WHERE h.organization_id=e.organization_id AND h.sender='codex'
 AND h.source_session_id=e.session_id AND h.state IN ('requested','acknowledged'))) AND (
 e.envelope->>'signal'='stop' OR NOT EXISTS (
 SELECT 1 FROM linear_bridge.codex_events a WHERE a.organization_id=e.organization_id AND a.app_user_id=e.app_user_id
 AND a.state IN ('dispatching','running','uncertain')))
 ORDER BY received_at,id LIMIT 1 FOR UPDATE SKIP LOCKED)
 UPDATE linear_bridge.codex_events e SET state='dispatching',updated_at=now()
 FROM candidate WHERE e.id=candidate.id RETURNING e.*,
 (SELECT a.id FROM linear_bridge.codex_events a WHERE a.organization_id=e.organization_id AND a.app_user_id=e.app_user_id
 AND a.session_id=e.session_id AND a.id<>e.id AND a.state='running' ORDER BY a.received_at DESC LIMIT 1) AS active_dispatch,
 (SELECT to_jsonb(h) FROM linear_bridge.native_handoffs h WHERE h.organization_id=e.organization_id AND h.recipient='codex'
 AND h.issue_id=(e.envelope->>'issue_id')::uuid AND (h.comment_id::text=e.envelope->>'origin_comment_id'
 OR h.target_session_id=e.session_id) ORDER BY h.created_at DESC LIMIT 1) AS correlated_handoff"""
    origin_query=('query CodexNativeOrigin($id:String!,$actor:String!){viewer{id organization{id}} '
        'sourceActor:user(id:$actor){id app} agentSession(id:$id){id appUser{id} issue{id} creator{id app} '
        'comment{id user{id app}} sourceComment{id user{id app}}}}')
    origin_prepare="""const row=$input.first().json;if(!row.id)return [];
return [{json:{...row,origin_request:{query:QUERY,variables:{id:row.session_id,
actor:row.envelope.source_actor_id||row.envelope.responsible_human_id||APP}}}}];""".replace('QUERY',json.dumps(origin_query)).replace('APP',json.dumps(app))
    origin_assess=(ROOT/'n8n_native_origin.js').read_text()+"\nconst policy="+json.dumps(policy)+";\n"+"""const row=$('Prepare Codex origin read').first().json;
const result=verifyOrigin(row.envelope,$input.first().json,policy,row.correlated_handoff);
return [{json:{...row,event_id:row.id,origin_permitted:result.permitted,origin_observation:result.observation,
correlated_handoff_id:result.correlated_handoff_id,
runtime_result:result.permitted?null:{dispatch:row.id,state:'failed',reason:'Native request origin unconfirmed; no coding turn was started.'}}}];"""
    origin_record=f"""WITH saved AS (UPDATE linear_bridge.codex_events SET origin_observation=$2::jsonb,
 runtime_result=CASE WHEN $4::boolean THEN runtime_result ELSE $5::jsonb END,updated_at=now()
 WHERE {select} AND id=$1::uuid AND state='dispatching' RETURNING *)
 SELECT saved.*,saved.id AS event_id,$4::boolean AS origin_permitted,$6::uuid AS active_dispatch,
 CASE WHEN $3::uuid IS NOT NULL AND $4::boolean THEN
 linear_bridge.native_handoff_bind('{org}'::uuid,'codex',$3::uuid,saved.session_id) ELSE NULL END AS handoff_binding
 FROM saved"""
    prepare="""const e=$input.first().json;
if (!e.id) return [];
const v=e.envelope;
const stop=v.signal==='stop', target=stop?e.active_dispatch:e.id;
return [{json:{event_id:e.id,target_dispatch:target,can_dispatch:!!target,
url:ORIGIN+(stop?'/v1/interrupt':'/v1/dispatch'),
request:stop?{dispatch_id:target}:{contract:'codex-dispatch.v1',dispatch_id:e.id,organization_id:v.organization_id,
app_user_id:v.app_user_id,session_id:v.session_id,issue_id:v.issue_id,message:v.message,binding:v.binding},
runtime_result:{state:'uncertain',reason:'No confirmed active runtime turn; reconcile.'}}}];""".replace('ORIGIN',json.dumps(c['runtime_origin'].rstrip('/')))
    assess="""const source=$(PREPARE).first().json;
const reply=$input.first().json, body=reply.body||{};
const states=['running','completed','failed','interrupted','uncertain','interrupt_requested'];
let result=(reply.statusCode>=200 && reply.statusCode<300 && body.dispatch===source.target_dispatch
 && states.includes(body.state))?body:{state:'uncertain',reason:'Runtime outcome unconfirmed; retain dispatch identity.'};
if(result.state==='interrupt_requested')result={...result,state:'running'};
return [{json:{event_id:source.event_id,runtime_result:result}}];"""
    finish=f"""WITH updated AS (
 UPDATE linear_bridge.codex_events SET state=$2::jsonb->>'state',runtime_result=$2::jsonb,updated_at=now()
 WHERE {select} AND id=$1::uuid RETURNING *)
 INSERT INTO linear_bridge.codex_outbox(organization_id,app_user_id,session_id,source_key,content)
 SELECT organization_id,app_user_id,session_id,'result:'||id::text||':'||state,
 jsonb_build_object('type',CASE WHEN state='completed' THEN 'response' WHEN state='uncertain' THEN 'thought' ELSE 'error' END,'body',
 CASE WHEN state='completed' THEN left(coalesce(runtime_result->>'result','Completed without a captured final response; inspect retained runtime evidence.'),10000)
 WHEN state='interrupted' THEN 'Codex turn interrupted.' WHEN state='uncertain' THEN 'Codex runtime outcome is uncertain; retained state needs reconciliation. Work has not been automatically rerun.'
 ELSE 'Codex runtime failed; inspect retained evidence.' END)
 FROM updated WHERE state IN ('completed','failed','interrupted','uncertain')
 AND (coalesce(envelope->>'signal','')<>'stop' OR state='uncertain')
 ON CONFLICT(organization_id,app_user_id,source_key) DO NOTHING"""
    repl='={{ [$json.event_id,JSON.stringify($json.runtime_result)] }}'
    dispatch_nodes=[schedule(),pg('Claim Codex dispatch',claim),code('Prepare Codex origin read',origin_prepare),
        http('Read native Codex origin','https://api.linear.app/graphql','={{ JSON.stringify($json.origin_request) }}',True),
        code('Verify native Codex origin',origin_assess),pg('Retain native origin observation',origin_record,
            '={{ [$json.event_id,JSON.stringify($json.origin_observation),$json.correlated_handoff_id,$json.origin_permitted,JSON.stringify($json.runtime_result),$json.active_dispatch] }}'),
        node('Native origin admitted','if',dict(conditions=dict(options=dict(typeValidation='strict'),
            conditions=[dict(id='origin',leftValue='={{ $json.origin_permitted }}',rightValue=True,
                operator=dict(type='boolean',operation='true',singleValue=True))],combinator='and'),options={})),
        code('Prepare Codex dispatch',prepare),
        node('Known target','if',dict(conditions=dict(options=dict(typeValidation='strict'),
            conditions=[dict(id='known',leftValue='={{ $json.can_dispatch }}',rightValue=True,
                             operator=dict(type='boolean',operation='true',singleValue=True))],combinator='and'),options={})),
        http('Dispatch fixed Codex runtime','={{ $json.url }}','={{ JSON.stringify($json.request) }}'),
        code('Assess dispatch',assess.replace('PREPARE',json.dumps('Prepare Codex dispatch'))),
        pg('Record dispatch outcome',finish,repl)]
    conn={a['name']:dict(main=[[dict(node=b['name'],type='main',index=0)]]) for a,b in zip(dispatch_nodes,dispatch_nodes[1:])}
    conn['Known target']=dict(main=[[dict(node='Dispatch fixed Codex runtime',type='main',index=0)],
                                  [dict(node='Record dispatch outcome',type='main',index=0)]])
    conn['Native origin admitted']=dict(main=[[dict(node='Prepare Codex dispatch',type='main',index=0)],
        [dict(node='Record dispatch outcome',type='main',index=0)]])
    dispatch=workflow('Codex Runtime Dispatch v0.4 (inactive)',dispatch_nodes,conn)
    poll=f"SELECT id AS event_id,coalesce(runtime_result->>'dispatch',id::text)::uuid AS target_dispatch FROM linear_bridge.codex_events WHERE {select} AND (state IN ('running','uncertain') OR (state='dispatching' AND updated_at<now()-interval '60 seconds')) ORDER BY updated_at,received_at LIMIT 1"
    reconcile=workflow('Codex Runtime Reconcile v0.4 (inactive)',[schedule(),pg('Select Codex runtime',poll),
        code('Require tracked Codex runtime','return $input.all().filter(x=>x.json.event_id && x.json.target_dispatch);'),
        http('Read fixed Codex runtime','={{ '+json.dumps(c['runtime_origin'].rstrip('/')+'/v1/runs/')+'+$json.target_dispatch }}'),
        code('Assess runtime',assess.replace('PREPARE',json.dumps('Select Codex runtime'))),
        pg('Record runtime outcome',finish,repl)])

    claim_out=f"""WITH candidate AS (SELECT id FROM linear_bridge.codex_outbox WHERE {select} AND state='pending'
 ORDER BY CASE WHEN source_key LIKE 'initial:%' THEN 0 ELSE 1 END,created_at LIMIT 1 FOR UPDATE SKIP LOCKED)
 UPDATE linear_bridge.codex_outbox o SET state='uncertain',reason='publication intent; remote outcome not yet confirmed',updated_at=now()
 FROM candidate WHERE o.id=candidate.id RETURNING o.*"""
    mutation='mutation CodexActivity($input:AgentActivityCreateInput!){agentActivityCreate(input:$input){success agentActivity{id}}}'
    check=f"""const row=$('Claim Codex reply').first().json, reply=$input.first().json;
const viewer=reply.body?.data?.viewer;
const permitted=reply.statusCode===200 && !reply.body?.errors && viewer?.id==={json.dumps(app)}
 && viewer?.organization?.id==={json.dumps(org)};
const publication_request={{query:{json.dumps(mutation)},variables:{{input:{{id:row.id,agentSessionId:row.session_id,content:row.content}}}}}};
return [{{json:{{...row,permitted,publication_request,publication_state:'dead_letter',reason:'Codex credential identity could not be verified'}}}}];"""
    # A UUID is frozen by the SQL row before publication. Lost HTTP results are
    # left uncertain; this workflow does not automatically resend them.
    # Keep GraphQL's adjacent closing braces out of n8n expression strings.
    # Construct the publication object in Code, then serialize only that field.
    publish_body='={{ JSON.stringify($json.publication_request) }}'
    outcome="""const row=$('Verify Codex actor').first().json, r=$input.first().json;
const data=r.body?.data?.agentActivityCreate;
const sent=r.statusCode===200 && !r.body?.errors && data?.success===true && data?.agentActivity?.id===row.id;
const errors=r.body?.errors;
const unavailable=Array.isArray(errors)&&errors.some(e=>/session/i.test(e.message||'')&&/expired|inactive|not found|unavailable/i.test(e.message||''));
return [{json:{id:row.id,publication_state:sent?'sent':unavailable?'dead_letter':'uncertain',
reason:sent?null:unavailable?'session_unavailable':'publication outcome unconfirmed; reconcile frozen activity UUID'}}];"""
    complete=f"UPDATE linear_bridge.codex_outbox SET state=$2,reason=$3,updated_at=now() WHERE {select} AND id=$1::uuid AND state='uncertain'"
    out_nodes=[schedule(),pg('Claim Codex reply',claim_out),
        code('Require pending Codex reply','return $input.all().filter(x=>x.json.id);'),
        http('Read Codex actor','https://api.linear.app/graphql',
             json.dumps(dict(query='query CodexViewer {viewer{id organization{id}}}')),True),
        code('Verify Codex actor',check),
        node('Correct Codex identity','if',dict(conditions=dict(options=dict(typeValidation='strict'),
            conditions=[dict(id='identity',leftValue='={{ $json.permitted }}',rightValue=True,
                operator=dict(type='boolean',operation='true',singleValue=True))],combinator='and'),options={})),
        http('Publish Codex activity','https://api.linear.app/graphql',publish_body,True),
        code('Assess Codex publication',outcome),
        pg('Retain publication outcome',complete,'={{ [$json.id,$json.publication_state,$json.reason] }}')]
    conn={a['name']:dict(main=[[dict(node=b['name'],type='main',index=0)]]) for a,b in zip(out_nodes,out_nodes[1:])}
    conn['Correct Codex identity']=dict(main=[[dict(node='Publish Codex activity',type='main',index=0)],
        [dict(node='Retain publication outcome',type='main',index=0)]])
    outbound=workflow('Codex Outbound v0.4 (inactive)',out_nodes,conn)
    registration=dict(name='Codex',actor='app',requested_scopes=SCOPES,
        callback_url=c['n8n_redirect_url'],webhook_url=c['verified_webhook_url'],
        webhook_types=['AgentSessionEvent'],install_now=False,preserve_existing_jarvis=True)
    return dict(contract='codex-n8n-package.v1',registration=registration,
        workflows=dict(inbound=inbound,dispatch=dispatch,reconcile=reconcile,outbound=outbound))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();result=render(json.loads(args.config.read_bytes()))
    args.output.mkdir(mode=0o700,parents=False,exist_ok=False)
    for key,value in result['workflows'].items():
        (args.output/(key+'.json')).write_text(json.dumps(value,indent=2)+'\n')
    (args.output/'registration.json').write_text(json.dumps(result['registration'],indent=2)+'\n')
    print(json.dumps(dict(rendered=True,active=False,workflows=4,registration_installed=False)))


if __name__=='__main__':main()
