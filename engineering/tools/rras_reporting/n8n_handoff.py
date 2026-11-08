"""Render inactive, fixed two-agent native handoff transport workflows."""
import importlib.util
import json
from pathlib import Path
import uuid


def local(name):
    spec=importlib.util.spec_from_file_location('n8n_handoff_'+name,Path(__file__).with_name(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def render(configuration):
    if (type(configuration) is not dict or set(configuration)!={'contract','policy','credentials'} or
            configuration['contract']!='native-handoff-n8n-config.v1'):raise ValueError('exact native handoff configuration required')
    m=local('native_handoff');policy=m.policy(configuration['policy']);refs=configuration['credentials']
    if type(refs) is not dict or set(refs)!={'postgres','jarvis_oauth','codex_oauth','jarvis_header','codex_header'}:
        raise ValueError('explicit separate n8n credential references required')
    ids=[]
    for key,value in refs.items():
        if key.endswith('_oauth'):
            if type(value) is not dict or set(value)!={'id','type'} or value['type'] not in ('oAuth2Api','linearOAuth2Api'):
                raise ValueError('reviewed n8n OAuth credential type required')
            value=value['id']
        if type(value) is not str or not value.strip() or len(value)>128:raise ValueError('bounded credential reference required')
        ids.append(value)
    if len(set(ids))!=len(ids):raise ValueError('distinct agent credential references required')
    org=policy['organization_id'];script=Path(__file__).with_name('n8n_native_handoff.js').read_text();workflows={}
    for role in ('jarvis','codex'):
        recipient='codex' if role=='jarvis' else 'jarvis'
        def node(name,kind,parameters,credential=None):
            value=dict(id=str(uuid.uuid5(uuid.NAMESPACE_URL,'rras:v04:handoff:'+role+':'+name)),name=name,
                type='n8n-nodes-base.'+kind,typeVersion={'webhook':2.1,'respondToWebhook':1.4,'postgres':2.6,
                    'httpRequest':4.2,'code':2,'scheduleTrigger':1.2,'if':2.2}[kind],position=[0,0],parameters=parameters)
            if credential:value['credentials']={credential[0]:dict(id=credential[1],name='Native handoff credential reference')}
            return value
        def code(name,body):return node(name,'code',dict(jsCode=body,mode='runOnceForAllItems'))
        def pg(name,query,replacements=None):return node(name,'postgres',dict(operation='executeQuery',query=query,
            options={} if replacements is None else dict(queryReplacement=replacements)),('postgres',refs['postgres']))
        def http(name,body,actor):
            credential=refs[actor+'_oauth'];kind=credential['type']
            auth=dict(authentication='genericCredentialType',genericAuthType='oAuth2Api') if kind=='oAuth2Api' else dict(
                authentication='predefinedCredentialType',nodeCredentialType='linearOAuth2Api')
            value=node(name,'httpRequest',dict(method='POST',url='https://api.linear.app/graphql',**auth,
                sendBody=True,contentType='raw',rawContentType='application/json',body=body,
                options=dict(timeout=15000,response=dict(response=dict(fullResponse=True,neverError=True)))),(kind,credential['id']))
            value.update(onError='continueRegularOutput',retryOnFail=False);return value
        def schedule():return node('Poll explicit handoffs','scheduleTrigger',dict(rule=dict(interval=[dict(field='seconds',secondsInterval=10)])))
        def permitted():return node('Correct native identity','if',dict(conditions=dict(options=dict(typeValidation='strict'),
            conditions=[dict(id='native-actor',leftValue='={{ $json.permitted }}',rightValue=True,
                operator=dict(type='boolean',operation='true',singleValue=True))],combinator='and'),options={}))
        def workflow(key,nodes):
            for i,n in enumerate(nodes):n['position']=[240*i,0]
            conn={a['name']:dict(main=[[dict(node=b['name'],type='main',index=0)]]) for a,b in zip(nodes,nodes[1:])}
            workflows[role+'_'+key]=dict(name=role.title()+' native handoff '+key+' v0.4 (inactive)',active=False,
                nodes=nodes,connections=conn,settings=dict(executionOrder='v1',saveDataErrorExecution='none',
                    saveDataSuccessExecution='none',saveManualExecutions=False,executionTimeout=60),tags=[],pinData={})
        admission=script+'\nconst policy='+json.dumps(policy)+';\n'+"const role="+json.dumps(role)+";\n"+(
            'return [{json:validateHandoff($input.first().json.body,policy,role)}];')
        workflow('request',[
            node('Scoped handoff request','webhook',dict(httpMethod='POST',path='rras-native-handoff-'+role,responseMode='responseNode',
                authentication='headerAuth',options={}),('httpHeaderAuth',refs[role+'_header'])),
            code('Validate fixed source context',admission),
            pg('Retain immutable handoff',f"SELECT linear_bridge.native_handoff_request('{org}'::uuid,'{role}',$1::jsonb,$2::text) AS request_id",
                '={{ [JSON.stringify($json.intent),$json.comment_body] }}'),
            node('Acknowledge staged handoff','respondToWebhook',dict(respondWith='json',
                responseBody='={{ {staged:true,request_id:$json.request_id,execution_started:false} }}',options=dict(responseCode=200)))])
        scoped=f"h.organization_id='{org}'::uuid AND h.sender='{role}'"
        claim=f"""WITH candidate AS (SELECT h.id,q.value FROM linear_bridge.native_handoffs h
 CROSS JOIN LATERAL (SELECT linear_bridge.native_handoff_quiescence(h.organization_id,h.sender,h.source_session_id) AS value) q
 WHERE {scoped} AND h.state='requested' AND h.comment_state='pending' AND q.value IS NOT NULL
 ORDER BY h.created_at,h.id LIMIT 1 FOR UPDATE OF h SKIP LOCKED)
 UPDATE linear_bridge.native_handoffs h SET comment_state='uncertain',source_quiescence=candidate.value,updated_at=now()
 FROM candidate WHERE h.id=candidate.id RETURNING h.*"""
        def verify(claim_name,actor,stage):
            query=m.COMMENT if stage=='comment' else m.SESSION
            value="{id:row.comment_id,issueId:row.issue_id,body:row.comment_body}" if stage=='comment' else "{commentId:row.comment_id}"
            return ("const row=$("+json.dumps(claim_name)+").first().json,r=$input.first().json,v=r.body?.data?.viewer;\n"+
                'const permitted=r.statusCode===200&&!r.body?.errors&&v?.id==='+json.dumps(policy['agents'][actor])+
                '&&v?.organization?.id==='+json.dumps(org)+';\n'+
                'return [{json:{...row,permitted,publication_request:{query:'+json.dumps(query)+',variables:{input:'+value+'}}}}];')
        def publication(key,claim_name,claim_sql,actor,stage):
            workflow(key,[schedule(),pg(claim_name,claim_sql),code('Require retained handoff','return $input.all().filter(x=>x.json.id);'),
                http('Read native publishing identity',json.dumps(dict(query=m.VIEWER)),actor),
                code('Verify separate native publisher',verify(claim_name,actor,stage)),permitted(),
                http('Publish one frozen native mutation','={{ JSON.stringify($json.publication_request) }}',actor),
                code('Leave outcome for exact readback','return [{json:{publication_attempted:true,outcome:"unconfirmed_pending_exact_readback",automatic_resend:false}}];')])
        publication('comment','Claim source comment',claim,role,'comment')
        session_claim=f"""WITH candidate AS (SELECT h.id FROM linear_bridge.native_handoffs h WHERE {scoped}
 AND h.state='requested' AND h.comment_state='confirmed' AND h.session_state='pending'
 ORDER BY h.updated_at,h.id LIMIT 1 FOR UPDATE SKIP LOCKED)
 UPDATE linear_bridge.native_handoffs h SET session_state='uncertain',updated_at=now() FROM candidate WHERE h.id=candidate.id RETURNING h.*"""
        publication('session','Claim recipient session',session_claim,recipient,'session')
        read_claim=f"""WITH candidate AS (SELECT h.id FROM linear_bridge.native_handoffs h WHERE {scoped}
 AND (h.comment_state='uncertain' OR h.session_state IN ('uncertain','bound')) AND h.state IN ('requested','acknowledged')
 ORDER BY h.updated_at,h.id LIMIT 1 FOR UPDATE SKIP LOCKED)
 UPDATE linear_bridge.native_handoffs h SET updated_at=now() FROM candidate WHERE h.id=candidate.id RETURNING h.*"""
        read_query=m.READ_COMMENT.replace('{comment(', '{viewer{id organization{id}} comment(',1)
        prepare_read='const row=$input.first().json;if(!row.id)return [];return [{json:{...row,read_request:{query:'+json.dumps(read_query)+',variables:{id:row.comment_id}}}}];'
        check_read="""const row=$('Prepare exact handoff read').first().json,r=$input.first().json,d=r.body?.data,c=d?.comment;
let confirmed=r.statusCode===200&&!r.body?.errors&&d?.viewer?.id===ACTOR&&d?.viewer?.organization?.id===ORG&&
c?.id===row.comment_id&&c?.body===row.comment_body&&c?.user?.id===row.body.sender_app_user_id&&c?.issue?.id===row.issue_id;
const page=c?.agentSessions,nodes=page?.nodes;
confirmed=confirmed&&page?.pageInfo?.hasNextPage===false&&Array.isArray(nodes)&&nodes.length<=50;
const targets=confirmed?nodes.filter(s=>s.appUser?.id===row.body.recipient_app_user_id):[];
confirmed=confirmed&&targets.length<=1&&targets.every(s=>s.issue?.id===row.issue_id);
return [{json:{id:row.id,confirmed,target_session_id:confirmed&&targets.length===1?targets[0].id:null}}];""".replace('ACTOR',json.dumps(policy['agents'][recipient])).replace('ORG',json.dumps(org))
        save_read=f"""WITH confirmed AS (UPDATE linear_bridge.native_handoffs h SET comment_state='confirmed',
 session_state=CASE WHEN session_state='bound' THEN 'bound' WHEN $3::uuid IS NOT NULL THEN 'uncertain'
 WHEN session_state='blocked' THEN 'pending' ELSE session_state END,updated_at=now()
 WHERE {scoped} AND h.id=$1::uuid AND $2::boolean AND h.source_quiescence IS NOT NULL RETURNING h.*)
 SELECT id,CASE WHEN $3::uuid IS NOT NULL THEN linear_bridge.native_handoff_bind(organization_id,recipient,id,$3::uuid)
 ELSE target_session_id END AS target_session_id FROM confirmed"""
        refresh=pg('Observe actual recipient runtime',f"SELECT linear_bridge.native_handoff_refresh(h.organization_id,h.id) FROM linear_bridge.native_handoffs h WHERE {scoped} AND h.session_state='bound' AND h.state IN ('requested','acknowledged') ORDER BY h.updated_at,h.id LIMIT 32")
        refresh['alwaysOutputData']=True
        workflow('reconcile',[schedule(),refresh,pg('Select exact handoff readback',read_claim),code('Prepare exact handoff read',prepare_read),
            http('Read exact source comment and recipient sessions','={{ JSON.stringify($json.read_request) }}',recipient),
            code('Verify exact native handoff evidence',check_read),pg('Retain confirmed native binding',save_read,
                '={{ [$json.id,$json.confirmed,$json.target_session_id] }}')])
    return dict(contract='native-handoff-n8n-package.v1',workflows=workflows,activation_authorized=False,
        required_sql='engineering/contracts/linear-native-handoff-v1.sql',native_acceptance_complete=False)
