"""Prepare a hash-checked inactive patch for the existing restricted Jarvis flow.

The original workflow remains a private operator snapshot. Only explicit mapped
engineering issues enter the new native-origin check. The original run request
and restrictions are retained, with additional engineering context instructions.
This module does not export credentials, call n8n, import or activate a workflow.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import uuid


def encoded(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()


def local(name):
    spec=importlib.util.spec_from_file_location('jarvis_admission_'+name,Path(__file__).with_name(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def render(snapshot,expected_sha256,configuration):
    if hashlib.sha256(encoded(snapshot)).hexdigest()!=expected_sha256:raise ValueError('existing workflow changed; inspect a fresh snapshot')
    package=local('n8n_handoff').render(configuration);policy=local('native_handoff').policy(configuration['policy'])
    result=json.loads(encoded(snapshot));nodes=result.get('nodes',[]);by_name={n['name']:n for n in nodes}
    names=('Normalize and Validate','Only New Deliveries','Start Restricted Hermes Run','Record Hermes Run')
    if (len(nodes)!=len(by_name) or any(name not in by_name for name in names) or
            by_name[names[0]]['type']!='n8n-nodes-base.code' or by_name[names[2]]['type']!='n8n-nodes-base.httpRequest' or
            result['connections'].get(names[1])!={'main':[[dict(node=names[2],type='main',index=0)]]}):
        raise ValueError('reviewed restricted Jarvis workflow topology required')
    start=by_name['Start Restricted Hermes Run'];body=start['parameters'].get('body','')
    prefix='={{ JSON.stringify(';suffix=') }}'
    if not body.startswith(prefix) or not body.endswith(suffix):raise ValueError('reviewed legacy JSON body expression required')
    if start['parameters'].get('url')!='http://hermes:8642/v1/runs':raise ValueError('reviewed existing private Hermes origin required')
    # A snapshot change requires renewed review; never silently replace an
    # arbitrary run instruction with an assumed equivalent restriction.
    required=('You are not authorized to modify repositories','run terminal commands','access files','deploy, merge, push','create an execution request')
    if any(text not in body for text in required):raise ValueError('existing restricted run policy differs')
    normal=by_name['Normalize and Validate']['parameters']['jsCode']
    issue_line='const issue = session.issue ?? body.issue ?? {};'
    if normal.count(issue_line)!=1:raise ValueError('reviewed existing normalizer required')
    # Native session-create-on-comment can supply issueId instead of issue.id.
    by_name['Normalize and Validate']['parameters']['jsCode']=normal.replace(issue_line,
        'const issue = session.issue ?? body.issue ?? {id: session.issueId};')
    fixed=dict(organization_id=policy['organization_id'],app_user_id=policy['agents']['jarvis'],
        agent_actor_ids=list(policy['agents'].values()),issues=policy['issues'])
    refs=configuration['credentials'];org=policy['organization_id']
    template=package['workflows']['jarvis_reconcile']
    def node(name,kind,parameters,credentials=None):
        value=dict(id=str(uuid.uuid5(uuid.NAMESPACE_URL,'rras:jarvis-admission:'+name)),name=name,
            type='n8n-nodes-base.'+kind,typeVersion={'code':2,'postgres':2.6,'httpRequest':4.2,'if':2.2}[kind],position=[0,0],parameters=parameters)
        if credentials:value['credentials']=credentials
        if name in by_name:raise ValueError('admission patch already present')
        nodes.append(value);by_name[name]=value;return value
    def code(name,text):return node(name,'code',dict(mode='runOnceForAllItems',jsCode=text))
    def pg(name,query,replacements):return node(name,'postgres',dict(operation='executeQuery',query=query,
        options=dict(queryReplacement=replacements)),{'postgres':dict(id=refs['postgres'],name='Reviewed existing PostgreSQL reference')})
    def decision(name):return node(name,'if',dict(conditions=dict(options=dict(typeValidation='strict'),conditions=[dict(id='admission',
        leftValue='={{ $json.engineering_permitted }}' if name=='Verified engineering origin' else '={{ $json.engineering_selected }}',
        rightValue=True,operator=dict(type='boolean',operation='true',singleValue=True))],combinator='and'),options={}))
    selection="""const delivery=$input.first().json,n=$('Normalize and Validate').first().json;
const policy=POLICY;const selected=Object.hasOwn(policy.issues,n.issueId);
if(selected&&n.organizationId!==policy.organization_id)throw new Error('Mapped engineering issue has the wrong organization');
const runBody=LEGACY;
let envelope=null;
if(selected){
 const raw=n.rawPayload,s=raw.agentSession??raw.data?.agentSession??{},a=raw.agentActivity??raw.data?.agentActivity??{};
 envelope={action:n.action,session_id:n.agentSessionId,issue_id:n.issueId,binding:policy.issues[n.issueId],
 source_actor_id:n.action==='prompted'?(a.userId??a.user?.id??null):null,
 origin_comment_id:s.sourceCommentId??s.commentId??s.sourceComment?.id??s.comment?.id??null,
 responsible_human_id:s.creatorId??s.creator?.id??null};
 runBody.instructions+=' Engineering context is explicit: '+JSON.stringify(envelope.binding)+
 '. You remain the Jarvis overall assistant. Codex is the engineering executor. Advice or an app message does not establish human architecture agreement or transfer coding ownership. '+
 'Keep handoffs on this exact work and architecture; use the scoped reporting/handoff adapter when installed. '+
 'Preserve unknown code baseline and source gaps. The existing repository, terminal, file, execution, merge and deployment restrictions still apply.';
}
return [{json:{...delivery,engineering_selected:selected,engineering_envelope:envelope,engineering_run_body:runBody}}];""".replace('POLICY',json.dumps(fixed)).replace('LEGACY',body[len(prefix):-len(suffix)])
    code('Select mapped engineering context',selection);decision('Mapped engineering issue')
    pg('Read retained Jarvis handoff',f"""SELECT $1::jsonb AS envelope,$2::uuid AS delivery_id,
 (SELECT to_jsonb(h) FROM linear_bridge.native_handoffs h WHERE h.organization_id='{org}'::uuid AND h.recipient='jarvis'
 AND h.issue_id=($1::jsonb->>'issue_id')::uuid AND (h.comment_id::text=$1::jsonb->>'origin_comment_id'
 OR h.target_session_id::text=$1::jsonb->>'session_id') ORDER BY h.created_at DESC LIMIT 1) AS correlated_handoff""",
        "={{ [JSON.stringify($json.engineering_envelope),$('Normalize and Validate').first().json.deliveryId] }}")
    query=local('native_handoff').READ_SESSION.replace('NativeHandoffReadSession','JarvisNativeOrigin',1)
    query=query.replace('($id:String!)','($id:String!,$actor:String!)').replace(' agentSession(', ' sourceActor:user(id:$actor){id app} agentSession(',1)
    code('Prepare Jarvis native origin',"const row=$input.first().json;return [{json:{...row,origin_request:{query:"+json.dumps(query)+
        ",variables:{id:row.envelope.session_id,actor:row.envelope.source_actor_id||row.envelope.responsible_human_id||"+json.dumps(fixed['app_user_id'])+"}}}}];")
    read=json.loads(encoded(next(n for n in template['nodes'] if n['name']=='Read exact source comment and recipient sessions')))
    read['id']=str(uuid.uuid5(uuid.NAMESPACE_URL,'rras:jarvis-admission:native-read'));read['name']='Read actual Jarvis native origin'
    # This query is made by Jarvis, not by the Codex recipient credential used
    # in the source-side Jarvis reconciliation template.
    oauth=refs['jarvis_oauth'];kind=oauth['type']
    read['credentials']={kind:dict(id=oauth['id'],name='Existing Jarvis OAuth reference')}
    read['parameters'].pop('genericAuthType',None);read['parameters'].pop('nodeCredentialType',None)
    read['parameters'].update(authentication='genericCredentialType' if kind=='oAuth2Api' else 'predefinedCredentialType',
        body='={{ JSON.stringify($json.origin_request) }}',**({'genericAuthType':kind} if kind=='oAuth2Api' else {'nodeCredentialType':kind}))
    nodes.append(read)
    verify=Path(__file__).with_name('n8n_native_origin.js').read_text()
    code('Verify Jarvis engineering origin',verify+'\nconst policy='+json.dumps(fixed)+";\n"+"""const row=$('Prepare Jarvis native origin').first().json;
const result=verifyOrigin(row.envelope,$input.first().json,policy,row.correlated_handoff);
return [{json:{...row,engineering_permitted:result.permitted,observation:result.observation,
binding_json:JSON.stringify(row.envelope.binding),handoff_id:result.correlated_handoff_id}}];""")
    pg('Retain Jarvis engineering admission',f"""SELECT linear_bridge.jarvis_engineering_admit($1::uuid,'{org}'::uuid,
 $2::uuid,$3::uuid,$4::boolean,$5::jsonb,$6::jsonb,$7::uuid) AS engineering_permitted""",
        '={{ [$json.delivery_id,$json.envelope.session_id,$json.envelope.issue_id,$json.engineering_permitted,JSON.stringify($json.observation),$json.binding_json,$json.handoff_id] }}')
    decision('Verified engineering origin')
    pg('Report unconfirmed engineering origin',"""INSERT INTO linear_bridge.outbox(idempotency_key,agent_session_id,event_type,payload)
 VALUES('engineering-origin-refused:'||$1::text,$2::text,'error',jsonb_build_object('body',
 'Jarvis could not confirm this engineering request against its native source and retained handoff. No assistant run was started; inspect the recorded admission evidence.',
 'source','jarvis-engineering-admission')) ON CONFLICT(idempotency_key) DO NOTHING""",
        "={{ [$('Normalize and Validate').first().json.deliveryId,$('Normalize and Validate').first().json.agentSessionId] }}")
    # The original HTTP method, origin, auth reference, headers, timeout and all
    # body fields remain unchanged. The selected context adds instructions only.
    start['parameters']['body']="={{ JSON.stringify($('Select mapped engineering context').first().json.engineering_run_body) }}"
    def edge(a,b,branch=0):
        connections=result['connections'];connections.setdefault(a,dict(main=[]))
        while len(connections[a]['main'])<=branch:connections[a]['main'].append([])
        connections[a]['main'][branch]=[dict(node=b,type='main',index=0)]
    edge('Only New Deliveries','Select mapped engineering context');edge('Select mapped engineering context','Mapped engineering issue')
    edge('Mapped engineering issue','Read retained Jarvis handoff');edge('Mapped engineering issue','Start Restricted Hermes Run',1)
    chain=['Read retained Jarvis handoff','Prepare Jarvis native origin','Read actual Jarvis native origin',
        'Verify Jarvis engineering origin','Retain Jarvis engineering admission','Verified engineering origin','Start Restricted Hermes Run']
    for a,b in zip(chain,chain[1:]):edge(a,b)
    edge('Verified engineering origin','Report unconfirmed engineering origin',1)
    result['active']=False
    # Caller must update the existing workflow ID under a checked version, not
    # import a duplicate webhook or assume preparing this patch activates it.
    return dict(contract='jarvis-engineering-admission-patch.v1',source_sha256=expected_sha256,
        workflow=result,activation_authorized=False,original_run_body_sha256=hashlib.sha256(body.encode()).hexdigest(),
        required_sql='engineering/contracts/linear-jarvis-engineering-admission-v1.sql')
