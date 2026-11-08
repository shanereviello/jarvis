"""Import retained native bridge transitions into owned, versioned handoff history."""
import copy
import importlib.util
from pathlib import Path
import uuid


def local(name):
    spec=importlib.util.spec_from_file_location('handoff_history_'+name,Path(__file__).with_name(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def configuration(value):
    if type(value) is not dict or set(value)!={'contract','policy','scope','contexts'} or value['contract']!='native-handoff-history-source.v1':
        raise ValueError('exact selected handoff history source required')
    policy=local('native_handoff').policy(value['policy']);rc=local('capture_intake').local('reporting_contract')
    if type(value['contexts']) is not dict or set(value['contexts'])!=set(policy['issues']):raise ValueError('complete explicit selected work contexts required')
    projects=set();count=0
    for issue,entries in value['contexts'].items():
        if type(entries) is not list or not 1<=len(entries)<=128:raise ValueError('explicit bounded retained context versions required')
        pins=[]
        for entry in entries:
            if type(entry) is not dict or set(entry)!={'binding','context'}:raise ValueError('exact retained binding/context pair required')
            pin=entry['binding'];context=entry['context'];count+=1
            if count>4096 or pin in pins:raise ValueError('bounded unique retained source pins required')
            pins.append(pin)
            local('native_handoff').policy(dict(policy,issues={issue:pin}))
            if any(pin[k]!=policy['issues'][issue][k] for k in ('project_id','work_id','plan_id')):
                raise ValueError('retained issue keeps its selected project/work/plan identity')
            probe=dict(contract='engineering-reporting.v1',operation='source.observe',client_event_key='handoff-source-validation',expected_head=None,
                scope=value['scope'],context=context,source=dict(kind='imported',namespace='n8n_native_handoff',id=issue),occurred_at=None,
                body=dict(source=dict(namespace='n8n_native_handoff',id=issue),source_observed_at=None,cursor=None,status='unknown',gaps=[],detail='Installed selected source validation only.'))
            rc.validate(probe)
            if (context is None or context['work'] is None or context['project_id']!=pin['project_id'] or
                    context['work']['work_item_id']!=pin['work_id'] or context['work']['work_revision_sha256']!=pin['work_revision_sha256'] or
                    context['architecture']['version']!=pin['architecture_version'] or context['architecture']['markdown_sha256']!=pin['architecture_sha256']):
                raise ValueError('exact native work/architecture context required')
            projects.add(context['project_id'])
        if policy['issues'][issue] not in pins:raise ValueError('installed current pin must have exact retained context')
    if len(projects)!=1:raise ValueError('one explicitly selected history project required')
    return copy.deepcopy(value)


def source_prefix(selected):return selected['policy']['organization_id']+':'+next(iter(selected['contexts'].values()))[0]['context']['project_id']+':'


def cursor(spool,selected):
    prefix=source_prefix(selected);after=0
    with spool.connection() as db:
        for row in db.execute("SELECT request FROM items WHERE kind='native_handoff'"):
            request=spool.c.decode(row[0]);source=request['source']['id']
            if source.startswith(prefix):after=max(after,int(source[len(prefix):]))
    return after


def stage(spool,selected,event):
    policy=selected['policy'];c=spool.c;native=local('native_handoff')
    if (type(event) is not dict or set(event)!={'sequence','id','organization_id','state','snapshot','observed_at'} or
            type(event['sequence']) is not int or not 1<=event['sequence']<2**53 or event['organization_id']!=policy['organization_id']):
        raise ValueError('exact selected native bridge event required')
    snapshot=event['snapshot'];intent=snapshot['body'];native.identifier(event['id'])
    candidates=[entry['context'] for entry in selected['contexts'].get(intent['issue_id'],[]) if entry['binding']==intent['binding']]
    if (snapshot['id']!=event['id'] or intent['id']!=event['id'] or snapshot['organization_id']!=event['organization_id'] or
            snapshot['state']!=event['state'] or snapshot['issue_id']!=intent['issue_id'] or intent['organization_id']!=event['organization_id'] or
            intent['sender'] not in ('jarvis','codex') or intent['recipient'] not in ('jarvis','codex') or intent['sender']==intent['recipient'] or
            intent['sender_app_user_id']!=policy['agents'][intent['sender']] or intent['recipient_app_user_id']!=policy['agents'][intent['recipient']] or
            intent.get('contract')!='native-agent-handoff.v1' or len(candidates)!=1 or intent['execution_authority_granted'] is not False or
            intent['human_approval_inferred'] is not False):raise ValueError('native event/work/identity binding differs')
    if any(snapshot[key]!=intent[key] for key in ('sender','recipient','source_session_id','comment_id','parent_handoff_id','depth')):
        raise ValueError('frozen source and native event identity differ')
    if len(c.encoded(event))>128*1024:raise ValueError('bounded native event required')
    context=candidates[0];source_id=source_prefix(selected)+str(event['sequence'])
    key='handoff-observe:'+c.digest(source_id.encode());digest=c.digest(c.encoded(event));entity='hof_'+uuid.UUID(intent['id']).hex
    with spool.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        old=db.execute('SELECT request FROM items WHERE key=?',(key,)).fetchone()
        if old:
            saved=c.decode(old['request'])
            if saved['context']!=context or not any(ref['namespace']=='native_handoff_event' and ref['sha256']==digest for ref in saved['body']['references']):
                raise ValueError('immutable native bridge event changed')
            return False
        prior=db.execute("SELECT sequence,request,request_sha256 FROM items WHERE kind='native_handoff' AND artifact=? ORDER BY sequence DESC LIMIT 1",(entity,)).fetchone()
        before=c.decode(prior['request']) if prior else None
        allowed={'requested':{'acknowledged','declined'},'acknowledged':{'completed'}}
        if (before and event['state'] not in allowed.get(before['body']['state'],set())) or (before is None and event['state']!='requested'):
            raise ValueError('complete ordered handoff transition evidence required')
        actor=lambda role:dict(role=role,runtime='linear_native_bridge',source_actor_id=policy['agents'][role])
        references=[dict(namespace='native_handoff_event',id=source_id,sha256=digest),
            dict(namespace='linear_comment',id=intent['comment_id'],sha256=None)]
        references.extend(intent['references'])
        if event['observed_at'] is not None:references.append(dict(namespace='bridge_observed_at',id=event['observed_at'],sha256=None))
        for observation in (snapshot.get('source_quiescence'),snapshot.get('recipient_observation')):
            if observation:
                key_name='dispatch_id' if observation.get('source')=='codex_runtime' else 'run_id'
                if observation.get(key_name):references.append(dict(namespace='runtime_dispatch' if key_name=='dispatch_id' else 'hermes_run',id=observation[key_name],sha256=None))
        body=dict(handoff_id=entity,version=before['body']['version']+1 if before else 1,
            previous_sha256=prior['request_sha256'] if prior else None,sender=actor(intent['sender']),recipient=actor(intent['recipient']),
            state=event['state'],source_session=dict(namespace='linear_agent',id=intent['source_session_id']),
            target_session=dict(namespace='linear_agent',id=snapshot['target_session_id']) if snapshot['target_session_id'] else None,
            issue_id=intent['issue_id'],requested_action=intent['requested_action'],result=snapshot.get('result'),references=references)
        body,_=local('capture_intake').redact_object(body)
        request=dict(contract='engineering-reporting.v1',operation='handoff.record',client_event_key=key,
            expected_head=body['previous_sha256'],scope=selected['scope'],context=context,
            source=dict(kind='imported',namespace='n8n_native_handoff',id=source_id),occurred_at=None,body=body)
        local('capture_intake').local('reporting_contract').validate(request)
        count=db.execute('SELECT count(*) FROM items').fetchone()[0]
        pending=db.execute("SELECT count(*) FROM items WHERE kind='artifact' AND receipt IS NULL").fetchone()[0]
        if count+2*pending+1>local('capture_intake').MAX_ITEMS:raise ValueError('handoff reporting capacity reached; retain native bridge events')
        spool.enqueue(db,request,'native_handoff',entity,depends=prior['sequence'] if prior else None);db.commit()
    local('capture_intake').sync(spool.root);return True


def poll(spool,value,query):
    selected=configuration(value);after=cursor(spool,selected);response=query(after)
    if type(response) is not dict or set(response)!={'contract','events'} or response['contract']!='native-handoff-event-page.v1' or type(response['events']) is not list or len(response['events'])>32:
        raise ValueError('bounded selected native event page required')
    staged=0;previous=after
    for event in response['events']:
        if type(event.get('sequence')) is not int or event['sequence']<=previous:raise ValueError('strictly advancing native cursor required')
        staged+=stage(spool,selected,event);previous=event['sequence']
    return dict(events_staged=staged,after=cursor(spool,selected),models_started=0)
