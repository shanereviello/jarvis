"""Runtime-owned start/progress/finish reporting and selected capture registration.

This adapter freezes private history requests locally; it makes no network call,
starts no model and does not treat runtime completion as work acceptance. History
delivery and selected-file collection run independently via bounded passive jobs.
"""
import hashlib
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re
import uuid


def local(name):
    spec=importlib.util.spec_from_file_location('runtime_reporting_'+name,Path(__file__).with_name(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def ident(prefix,value):return prefix+uuid.uuid5(uuid.NAMESPACE_URL,value).hex


class Reporter:
    def __init__(self,configuration,policy):
        intake=local('capture_intake');self.intake=intake;self.c=intake.local('contract');rc=intake.local('reporting_contract')
        required={'contract','spool','scope','contexts','host_identity','oauth_client_id','capture'}
        if (type(configuration) is not dict or not required<=set(configuration) or set(configuration)-required-{'task_contexts'} or
                configuration['contract']!='codex-runtime-reporting.v1' or type(configuration['contexts']) is not dict or
                set(configuration['contexts'])!=set(policy['issues'])):raise ValueError('exact runtime reporting context required')
        self.configuration=configuration;self.policy=policy;self.spool=intake.Spool(configuration['spool'])
        for issue,ctx in configuration['contexts'].items():
            pin=policy['issues'][issue]
            if (ctx is None or ctx.get('work') is None or ctx['project_id']!=pin['project_id'] or
                    ctx['work']['work_item_id']!=pin['work_id'] or ctx['work']['work_revision_sha256']!=pin['work_revision_sha256'] or
                    ctx['architecture']['version']!=pin['architecture_version'] or ctx['architecture']['markdown_sha256']!=pin['architecture_sha256']):
                raise ValueError('runtime/reporting work or architecture pin differs')
            probe=dict(contract='engineering-reporting.v1',operation='source.observe',client_event_key='runtime-config',
                expected_head=None,scope=configuration['scope'],context=ctx,source=dict(kind='agent_reported',namespace='codex_runtime',id=None),
                occurred_at=None,body=dict(source=dict(namespace='codex_runtime',id=issue),status='unknown',source_observed_at=None,
                    cursor=None,gaps=[],detail='Installed configuration validation only.'))
            rc.validate(probe)
        if configuration['host_identity'] is not None and (type(configuration['host_identity']) is not str or not 1<=len(configuration['host_identity'])<=256):
            raise ValueError('bounded configured host identity required')
        client=configuration['oauth_client_id']
        if client is not None and (type(client) is not str or not re.fullmatch('(?:[0-9a-f]{32}|[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})',client)):
            raise ValueError('exact public OAuth client ID or unknown required')
        capture=configuration['capture']
        if capture is not None:
            if type(capture) is not dict or set(capture)!={'binary','native_root','jobs','authorization_reference','service_socket','service_uid'}:
                raise ValueError('exact selected capture registration policy required')
            local('capture_collectors').authorization(capture['authorization_reference'])
            for key in ('binary','native_root','jobs','service_socket'):
                p=Path(capture[key])
                if not p.is_absolute() or p.resolve()!=p:raise ValueError('canonical capture registration paths required')
            intake.private(capture['jobs'],True)
            if type(capture['service_uid']) is not int or capture['service_uid']<0:raise ValueError('exact history service UID required')
        self.task_contexts={}
        if 'task_contexts' in configuration:
            if type(configuration['task_contexts']) is not dict or set(configuration['task_contexts'])!=set(policy['issues']):
                raise ValueError('every installed issue requires exact retained task context')
            for issue,value in configuration['task_contexts'].items():self.task_contexts[issue]=local('runtime_task_context').validate(value,configuration['scope'],configuration['contexts'][issue])

    def task_instructions(self,issue):
        return local('runtime_task_context').instructions(self.task_contexts[issue]) if issue in self.task_contexts else ''

    def request(self,row,operation,body,*,expected=None,key=None):
        value=dict(contract='engineering-reporting.v1',operation=operation,client_event_key=key or 'runtime:'+self.c.digest(self.c.encoded(
            dict(dispatch=row['dispatch'],operation=operation,body=body))),expected_head=expected,
            scope=self.configuration['scope'],context=self.configuration['contexts'][row['issue']],
            source=dict(kind='agent_reported',namespace='codex_runtime_adapter',id=row['dispatch']),occurred_at=None,body=body)
        return self.intake.local('reporting_contract').validate(value)

    def append(self,db,request,entity=None):
        count=db.execute('SELECT count(*) FROM items').fetchone()[0]
        pending=db.execute("SELECT count(*) FROM items WHERE kind='artifact' AND receipt IS NULL").fetchone()[0]
        old=db.execute('SELECT sequence,request FROM items WHERE key=?',(request['client_event_key'],)).fetchone()
        if old:
            if old['request']!=self.c.encoded(request):raise ValueError('runtime reporting key changed')
            return old['sequence']
        if count+2*pending+1>self.intake.MAX_ITEMS:raise ValueError('runtime reporting queue capacity reached; retain runtime journal')
        prior=db.execute("SELECT sequence FROM items WHERE kind='runtime' AND artifact=? ORDER BY sequence DESC LIMIT 1",(entity,)).fetchone() if entity else None
        return self.spool.enqueue(db,request,'runtime',entity,depends=prior[0] if prior else None)

    def attempt(self,db,row,phase,actor,metadata):
        aid=ident('att_','codex-runtime:'+self.policy['organization_id']+':'+self.policy['app_user_id']+':'+row['dispatch'])
        prior=db.execute("SELECT request,request_sha256 FROM items WHERE kind='runtime' AND artifact=? ORDER BY sequence DESC LIMIT 1",(aid,)).fetchone()
        old=self.c.decode(prior['request']) if prior else None
        sessions=[dict(namespace='linear_agent',id=row['session'])]
        if row['thread']:sessions.append(dict(namespace='codex',id=row['thread']))
        result={'started':'Retained authorized dispatch intent; work acceptance and native start timing are not inferred.',
            'progress':'Native turn is active; current thread/turn references are retained.',
            'paused':'Runtime outcome is uncertain or cancellation is pending; no automatic rerun is authorized.',
            'completed':'Native turn completed; independent validation, work acceptance, merge and deployment remain separate.',
            'failed':'Native runtime reported failure; this is not a new retry authorization.',
            'interrupted':'Native runtime reported an interrupted turn; work outcome remains separate.'}[phase]
        baseline=(metadata.get('gitInfo') or {}).get('sha')
        if (self.configuration['scope']['kind']!='repository' or type(baseline) is not str or
                not re.fullmatch('[0-9a-f]{40}',baseline)):baseline=None
        if baseline:result+=' Baseline is native thread metadata, not a fresh per-turn checkout audit.'
        body=dict(attempt_id=aid,version=old['body']['version']+1 if old else 1,
            previous_sha256=prior['request_sha256'] if prior else None,phase=phase,actor=actor,coordinator=None,
            sessions=sessions,baseline_commit=baseline,result=result,references=[dict(namespace='runtime_dispatch',id=row['dispatch'],sha256=row['digest'])])
        comparable={k:v for k,v in body.items() if k not in ('version','previous_sha256')}
        if old and comparable=={k:v for k,v in old['body'].items() if k not in ('version','previous_sha256')}:return aid
        if old and old['body']['phase'] in ('completed','failed'):
            raise ValueError('terminal attempt cannot be silently reopened')
        self.append(db,self.request(row,'attempt.record',body,expected=body['previous_sha256']),aid)
        return aid

    def register_capture(self,row,metadata):
        selected=self.configuration['capture']
        if selected is None or metadata.get('path') is None:return False
        job,digest=self.capture_job(row,metadata['path'])
        directory=Path(selected['jobs']);lock=directory/'.registry.lock'
        fd=os.open(lock,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
        try:
            self.intake.private(lock);fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            paths=[]
            with os.scandir(directory) as entries:
                for entry in entries:
                    if entry.name in ('.registry.lock','.cursor.json'):continue
                    if not re.fullmatch('[0-9a-f]{64}\\.json',entry.name):raise ValueError('unexpected capture registry member')
                    paths.append(entry.name)
                    if len(paths)>4096:raise ValueError('capture registry capacity reached; retain native source')
            path=directory/(digest+'.json');raw=self.c.encoded(job)
            if path.exists() or path.is_symlink():
                self.intake.private(path)
                if path.read_bytes()!=raw:raise ValueError('selected native capture registration changed')
            else:
                if len(paths)>=4096:raise ValueError('capture registry capacity reached; retain native source')
                out=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
                with os.fdopen(out,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
                self.intake.sync(path.parent)
        finally:os.close(fd)
        return True

    def capture_job(self,row,source):
        selected=self.configuration['capture']
        if selected is None:raise ValueError('selected capture not installed')
        source=Path(source);native_root=Path(selected['native_root'])
        if (not source.is_absolute() or source.resolve()!=source or not source.is_relative_to(native_root) or
                not re.fullmatch('[0-9a-f-]{36}',row['thread'])):raise ValueError('selected native thread source differs')
        local('codex_runtime').identifier(row['session']);local('codex_runtime').identifier(row['thread'])
        ctx=self.configuration['contexts'][row['issue']]
        job=dict(contract='engineering-capture-jobs.v1',spool=str(self.spool.root),service_socket=selected['service_socket'],
            service_uid=selected['service_uid'],jobs=[dict(id='runtime-'+row['session'],source=str(source),session=row['thread'],
                binary=selected['binary'],scope=self.configuration['scope'],context=ctx,authorization_reference=selected['authorization_reference'])])
        digest=self.c.digest(self.c.encoded(dict(session=row['session'],thread=row['thread'],context=ctx)))
        return job,digest

    def observe(self,runtime,dispatch):
        # Called only after runtime transactions have committed. This local read
        # does not instantiate another Runtime or acquire its process lock.
        with runtime.connection() as native:
            row=native.execute('SELECT * FROM turns WHERE dispatch=?',(dispatch,)).fetchone()
            if row is None:raise ValueError('retained dispatch required')
            metadata={}
            for value in native.execute('SELECT body FROM events WHERE dispatch=? ORDER BY sequence DESC',(dispatch,)):
                event=self.c.decode(value[0])
                if event.get('method')=='adapter/threadMetadata':metadata=event['params'];break
        if runtime.policy!=self.policy:raise ValueError('runtime reporting policy changed')
        actor=dict(role='codex',runtime='codex_app_server',source_actor_id=self.policy['app_user_id'])
        phase={'preparing':'started','running':'progress','uncertain':'paused','interrupt_requested':'paused',
            'completed':'completed','failed':'failed','interrupted':'interrupted'}[row['state']]
        with self.spool.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            aid=ident('att_','codex-runtime:'+self.policy['organization_id']+':'+self.policy['app_user_id']+':'+dispatch)
            exists=db.execute("SELECT 1 FROM items WHERE artifact=? AND kind='runtime'",(aid,)).fetchone()
            if not exists:self.attempt(db,row,'started',actor,{})
            self.attempt(db,row,phase,actor,metadata)
            if row['thread']:
                sid=ident('ses_','codex-native:'+self.policy['app_user_id']+':'+row['thread'])
                exists=db.execute("SELECT 1 FROM items WHERE artifact=? AND kind='runtime'",(sid,)).fetchone()
                if not exists:
                    model=metadata.get('model');model=model if type(model) is str and model.strip() else None
                    body=dict(session_record_id=sid,version=1,previous_sha256=None,session=dict(namespace='codex',id=row['thread']),actor=actor,
                        linear_agent_session_id=row['session'],linear_agent_activity_id=None,oauth_client_id=self.configuration['oauth_client_id'],
                        native_session_tree_id=metadata.get('sessionId'),parent_native_thread_id=metadata.get('parentThreadId'),
                        forked_from_native_thread_id=metadata.get('forkedFromId'),host_identity=self.configuration['host_identity'],
                        workspace_identity=self.policy['cwd'],source_version=metadata.get('cliVersion'),model=model,
                        model_basis='configured_thread' if model else 'unknown',tokens=None,cost_usd=None,
                        limitations=['Thread model is configuration metadata, not per-turn model execution telemetry.',
                            'Tokens, cost and missing lineage remain unknown; receipt time is not native occurrence time.'])
                    self.append(db,self.request(row,'session.describe',body),sid)
                body=dict(session=dict(namespace='codex',id=row['thread']),relationship='attached',related_session=None,
                    attempt_id=aid,actor=actor,reason='Actual native thread is bound to this retained dispatch/Linear agent session; session-level context is not universal message attribution.')
                self.append(db,self.request(row,'session.relate',body))
            if phase in ('started','completed','failed','interrupted','paused'):
                text=(row['result'] or '')[:3000]
                identity=self.c.digest(self.c.encoded(dict(state=row['state'],excerpt=text)))
                body=dict(report_id=ident('rpt_','runtime-checkpoint:'+dispatch+':'+phase+':'+identity),attempt_id=aid,
                    observations=['Runtime state: '+row['state']]+(['Visible result excerpt: '+text] if text else []),
                    alternatives_and_reasons=[],changes=[],validation=[dict(result='not_run',description='Runtime state does not establish independent acceptance, merge or deployment.',references=[])],
                    open_questions=['Review native capture coverage and independent validation before work closeout.'],
                    next_step='Continue the known authorized work or inspect the retained terminal/uncertain state; do not rerun work to repair reporting.',
                    references=[dict(namespace='runtime_dispatch',id=dispatch,sha256=row['digest'])])
                body,_=self.intake.redact_object(body)
                self.append(db,self.request(row,'checkpoint.report',body))
            db.commit()
        self.intake.sync(self.spool.root)
        selected=self.register_capture(row,metadata) if row['thread'] else False
        return dict(staged=True,capture_registered=selected,network_calls=0)
