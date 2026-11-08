"""Passive native Jarvis lifecycle/checkpoint import through owned-history API.

Retained admission is an intent, not proof of model execution. Native completion
does not accept the engineering work or transfer coder ownership. No source
reader in this module starts an agent, accesses native credentials or mutates SQL.
"""
import copy
import importlib.util
import os
from pathlib import Path
import re


def local(name):
    spec=importlib.util.spec_from_file_location('hermes_history_'+name,Path(__file__).with_name(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def configuration(value):
    if type(value) is not dict or value.get('contract')!='hermes-runtime-history-source.v1':raise ValueError('selected native history source required')
    checked=local('handoff_history').configuration(dict(value,contract='native-handoff-history-source.v1'))
    checked['contract']=value['contract'];return checked


def prefix(selected):return local('handoff_history').source_prefix(selected)


def cursor(spool,selected):
    path=spool.root/'hermes-cursor.json'
    if path.with_suffix('.pending').exists() or path.with_suffix('.pending').is_symlink():raise ValueError('interrupted native cursor requires inspection')
    expected=spool.c.digest(spool.c.encoded(selected))
    if not path.exists() and not path.is_symlink():return dict(selection_sha256=expected,after_admission=0,after_run=0,after_checkpoint=0)
    local('capture_intake').private(path);value=spool.c.decode(path.read_bytes())
    if (type(value) is not dict or set(value)!={'selection_sha256','after_admission','after_run','after_checkpoint'} or
            value['selection_sha256']!=expected or any(type(value[k]) is not int or not 0<=value[k]<2**53
                for k in ('after_admission','after_run','after_checkpoint'))):raise ValueError('retained selected native cursor differs')
    return value


def save_cursor(spool,value):
    path=spool.root/'hermes-cursor.json';temporary=path.with_suffix('.pending');raw=spool.c.encoded(value)
    if path.exists() and path.read_bytes()==raw:return
    fd=os.open(temporary,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    os.replace(temporary,path);local('capture_intake').sync(spool.root)


def context(selected,event):
    if (event['organization_id']!=selected['policy']['organization_id'] or type(event['sequence']) is not int or
            not 1<=event['sequence']<2**53):raise ValueError('selected native source differs')
    for key in ('organization_id','delivery_id','session_id','issue_id'):local('native_handoff').identifier(event[key])
    if event['handoff_id'] is not None:local('native_handoff').identifier(event['handoff_id'])
    candidates=[entry['context'] for entry in selected['contexts'].get(event['issue_id'],[]) if entry['binding']==event['binding']]
    if len(candidates)!=1:raise ValueError('exact retained native work/architecture context required')
    return candidates[0]


def actor(selected):return dict(role='jarvis',runtime='hermes_api',source_actor_id=selected['policy']['agents']['jarvis'])


def attempt_id(selected,delivery):
    return local('runtime_reporting').ident('att_','hermes-runtime:'+selected['policy']['organization_id']+':'+selected['policy']['agents']['jarvis']+':'+delivery)


def request(selected,ctx,operation,body,key,delivery,expected=None):
    value=dict(contract='engineering-reporting.v1',operation=operation,client_event_key=key,expected_head=expected,
        scope=selected['scope'],context=ctx,source=dict(kind='imported',namespace='n8n_hermes_runtime',id=delivery),occurred_at=None,body=body)
    return local('capture_intake').local('reporting_contract').validate(value)


def append(spool,db,value,kind,entity=None,depends=None):
    intake=local('capture_intake')
    old=db.execute('SELECT sequence,request FROM items WHERE key=?',(value['client_event_key'],)).fetchone()
    if old:
        if old['request']!=spool.c.encoded(value):raise ValueError('native history event identity changed')
        return old['sequence']
    count=db.execute('SELECT count(*) FROM items').fetchone()[0]
    pending=db.execute("SELECT count(*) FROM items WHERE kind='artifact' AND receipt IS NULL").fetchone()[0]
    if count+2*pending+1>intake.MAX_ITEMS:raise ValueError('native history queue full; retain transport evidence')
    return spool.enqueue(db,value,kind,entity,depends=depends)


def previous(spool,db,entity):
    prior=db.execute("SELECT sequence,request,request_sha256 FROM items WHERE kind='hermes_attempt' AND artifact=? ORDER BY sequence DESC LIMIT 1",(entity,)).fetchone()
    return prior,spool.c.decode(prior['request']) if prior else None


def stage_attempt(spool,selected,event,ctx,*,run=False):
    fields={'sequence','delivery_id','organization_id','session_id','issue_id','binding','handoff_id'}
    fields|={'run_id','hermes_session_id','status','recorded_at','admitted_at','completed_at'} if run else {'observed_at'}
    if set(event)!=fields:raise ValueError('exact native lifecycle row required')
    for key in (('recorded_at','admitted_at') if run else ('observed_at',)):
        if local('capture_collectors').source_time(event[key]) is None:raise ValueError('exact bridge observation time required')
    if run and event['completed_at'] is not None and local('capture_collectors').source_time(event['completed_at']) is None:
        raise ValueError('exact bridge completion observation time required')
    aid=attempt_id(selected,event['delivery_id']);a=actor(selected)
    sessions=[dict(namespace='linear_agent',id=event['session_id'])]
    coordinator=dict(role='codex',runtime='linear_native_bridge',source_actor_id=selected['policy']['agents']['codex']) if event['handoff_id'] else None
    start=dict(attempt_id=aid,version=1,previous_sha256=None,phase='started',actor=a,coordinator=coordinator,sessions=sessions,
        baseline_commit=None,result='Retained admitted restricted Jarvis request; model execution and native start time are not established.',
        references=[dict(namespace='linear_delivery',id=event['delivery_id'],sha256=None)])
    with spool.connection() as db:
        db.execute('BEGIN IMMEDIATE');prior,before=previous(spool,db,aid)
        if before is None:
            append(spool,db,request(selected,ctx,'attempt.record',start,'hermes-start:'+event['delivery_id'],event['delivery_id']),'hermes_attempt',aid)
            prior,before=previous(spool,db,aid)
            pending=dict(source=dict(namespace='n8n_hermes_request',id=event['delivery_id']),source_observed_at=None,
                cursor=None,status='pending',gaps=['Native runtime binding and execution are not yet confirmed.'],
                detail='Retained admitted assistant request; source observation is asynchronous and grants no execution authority. Bridge admission observed_at: '+event['admitted_at' if run else 'observed_at'])
            append(spool,db,request(selected,ctx,'source.observe',pending,'hermes-pending:'+event['delivery_id'],event['delivery_id']),
                'hermes_admission_observation',event['delivery_id'],prior['sequence'])
        if before['context']!=ctx:raise ValueError('retained native attempt context changed')
        if not run:db.commit();return aid
        status=event['status'];phase={'started':'progress','running':'progress','completed':'completed','failed':'failed',
            'interrupted':'interrupted','cancelled':'interrupted'}.get(status,'paused')
        if phase in ('completed','failed','interrupted') and event['completed_at'] is None:phase='paused'
        if type(status) not in (str,type(None)) or (status is not None and len(status.encode())>128):raise ValueError('bounded native status required')
        parsed=local('hermes_native_context').parse('api_server',event['hermes_session_id'],event['run_id'])
        if parsed['organization_id']!=event['organization_id'] or parsed['session_id']!=event['session_id']:raise ValueError('native session/run binding differs')
        body=dict(start,version=before['body']['version']+1,previous_sha256=prior['request_sha256'],phase=phase,
            sessions=sessions+[dict(namespace='hermes_api_session_key',id=event['hermes_session_id']),dict(namespace='hermes_run',id=event['run_id'])],
            result='Observed retained assistant-run transport status: '+str(status)+'. Native timing, model usage and independent work acceptance are not established. Engineering ownership and existing permissions remain separate.',
            references=start['references']+[dict(namespace='hermes_run',id=event['run_id'],sha256=None)])
        comparable=lambda value:{k:v for k,v in value.items() if k not in ('version','previous_sha256')}
        conflict=comparable(body)!=comparable(before['body']) and before['body']['phase'] in ('completed','failed','interrupted')
        if comparable(body)!=comparable(before['body']) and not conflict:
            key='hermes-phase:'+spool.c.digest(spool.c.encoded(dict(delivery=event['delivery_id'],body=body)))
            append(spool,db,request(selected,ctx,'attempt.record',body,key,event['delivery_id'],body['previous_sha256']),'hermes_attempt',aid,prior['sequence'])
        prior,_=previous(spool,db,aid)
        # Preserve the source row independently of the attempt's state. A late
        # contradictory bridge status becomes a gap, never a reopened executor.
        detail='Retained bridge row; timestamps describe transport records, not native execution timing. '+spool.c.encoded(event).decode().strip()
        gaps=(['Retained terminal attempt conflicts with a later bridge status; no executor was reopened.'] if conflict else
            ['Native transport outcome is unknown or lacks a completion timestamp; no automatic rerun.'] if phase=='paused' else [])
        source=dict(source=dict(namespace='n8n_hermes_request',id=event['delivery_id']),source_observed_at=None,
            cursor=spool.c.digest(spool.c.encoded(event)),status='gap' if gaps else 'current',gaps=gaps,detail=detail)
        append(spool,db,request(selected,ctx,'source.observe',source,'hermes-row:'+source['cursor'],event['delivery_id']),
            'hermes_run_observation',event['run_id'],prior['sequence'])
        relation=dict(session=dict(namespace='hermes_api_session_key',id=event['hermes_session_id']),relationship='attached',related_session=None,
            attempt_id=aid,actor=a,reason='Actual retained restricted assistant run; session attachment is context, not universal work ownership.')
        append(spool,db,request(selected,ctx,'session.relate',relation,'hermes-session:'+event['run_id'],event['delivery_id']),
            'hermes_session',event['run_id'],prior['sequence'])
        db.commit()
    return aid


def stage_checkpoint(spool,selected,event,runs):
    required={'sequence','id','run_id','organization_id','issue_id','report_json','report_sha256','observed_at'}
    if (type(event) is not dict or set(event)!=required or type(event['sequence']) is not int or not 1<=event['sequence']<2**53 or
            event['organization_id']!=selected['policy']['organization_id'] or type(event['report_json']) is not str):
        raise ValueError('exact selected native checkpoint required')
    native=local('native_handoff');native.identifier(event['id']);raw=event['report_json'].encode()
    if len(raw)>32768 or spool.c.digest(raw)!=event['report_sha256']:raise ValueError('retained native checkpoint digest differs')
    run=runs.get(event['run_id'])
    if not run or run['issue_id']!=event['issue_id']:raise ValueError('checkpoint requires its exact retained run')
    ctx=context(selected,run);value=spool.c.decode(raw);aid=attempt_id(selected,run['delivery_id'])
    if (value.get('operation')!='checkpoint.report' or value.get('scope')!=selected['scope'] or value.get('context')!=ctx or
            value.get('client_event_key')!='hermes-native:'+event['id'] or value.get('expected_head') is not None or
            value.get('source')!=dict(kind='agent_reported',namespace='hermes_runtime_adapter',id=event['run_id']) or
            value.get('occurred_at') is not None or value.get('body',{}).get('attempt_id')!=aid or
            value.get('body',{}).get('report_id')!=local('runtime_reporting').ident('rpt_','hermes-checkpoint:'+event['id'])):
        raise ValueError('native checkpoint attribution or context differs')
    value,_=local('capture_intake').redact_object(value);local('capture_intake').local('reporting_contract').validate(value)
    with spool.connection() as db:
        db.execute('BEGIN IMMEDIATE');prior,_=previous(spool,db,aid)
        if prior is None:raise ValueError('native lifecycle must precede its checkpoint')
        append(spool,db,value,'hermes_checkpoint',event['id'],prior['sequence']);db.commit()


def poll(spool,value,query):
    selected=configuration(value);old=cursor(spool,selected);reply=query({k:v for k,v in old.items() if k!='selection_sha256'})
    keys={'contract','admissions','runs','checkpoints','next_admission_after','next_run_after','next_checkpoint_after'}
    if (type(reply) is not dict or set(reply)!=keys or reply['contract']!='hermes-runtime-history-page.v1' or
            any(type(reply[k]) is not list or len(reply[k])>limit for k,limit in (('admissions',16),('runs',32),('checkpoints',16))) or
            len(spool.c.encoded(reply))>1024*1024):raise ValueError('bounded selected native history page required')
    for key in ('admission','run','checkpoint'):
        count=reply['next_'+key+'_after']
        if type(count) is not int or not 0<=count<2**53 or (key!='run' and count<old['after_'+key]):raise ValueError('native cursor regressed')
    for event in reply['admissions']:
        if event['sequence']<=old['after_admission']:raise ValueError('admission cursor did not advance')
        stage_attempt(spool,selected,event,context(selected,event))
    runs={}
    for event in reply['runs']:
        if event['run_id'] in runs:raise ValueError('duplicate native run in page')
        stage_attempt(spool,selected,event,context(selected,event),run=True);runs[event['run_id']]=event
    for event in reply['checkpoints']:
        if event['sequence']<=old['after_checkpoint']:raise ValueError('checkpoint cursor did not advance')
        stage_checkpoint(spool,selected,event,runs)
    for key in ('admission','checkpoint'):
        rows=reply['admissions' if key=='admission' else 'checkpoints'];expected=max([row['sequence'] for row in rows]+[old['after_'+key]])
        if reply['next_'+key+'_after']!=expected:raise ValueError('native cursor skipped an unseen record')
        sequences=[row['sequence'] for row in rows]
        if sequences!=sorted(set(sequences)):raise ValueError('native source cursor is not strictly ordered')
    if reply['next_run_after'] and reply['next_run_after'] not in [row['sequence'] for row in reply['runs']]:
        raise ValueError('native run cursor skipped an unseen row')
    save_cursor(spool,dict(selection_sha256=old['selection_sha256'],**{'after_'+k:reply['next_'+k+'_after'] for k in ('admission','run','checkpoint')}))
    return dict(admissions=len(reply['admissions']),runs=len(reply['runs']),checkpoints=len(reply['checkpoints']),models_started=0)
