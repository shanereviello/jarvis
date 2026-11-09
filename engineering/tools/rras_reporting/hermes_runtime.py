"""Native Jarvis reporting tools: bound context, private queue, no coding tools.

The existing native gateway supplies identity. Agent arguments contain prose
only. Passive delivery resolves the retained engineering-run binding through
n8n, which retains the native OAuth credentials and work mapping.
"""
import hashlib
import fcntl
import http.client
import importlib.util
import json
import logging
import os
import threading
from pathlib import Path
from urllib.parse import urlsplit
from jsonschema import Draft202012Validator


def local(name):
    spec=importlib.util.spec_from_file_location('hermes_runtime_'+name,Path(__file__).with_name(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def schema(operation):
    if operation=='checkpoint':return local('runtime_checkpoint_mcp').checkpoint_schema()
    if operation=='handoff':return local('runtime_handoff').schema()
    raise ValueError('only checkpoint and handoff reporting available')


def transport(origin,token):
    parsed=urlsplit(origin)
    if (parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or
            parsed.path not in ('','/') or type(token) is not bytes or not 32<=len(token)<=256 or not all(33<=v<=126 for v in token)):
        raise ValueError('fixed private native reporting transport required')
    paths={'context':'/webhook/rras-jarvis-engineering-context','checkpoint':'/webhook/rras-jarvis-engineering-checkpoint','handoff':'/webhook/rras-native-handoff-jarvis'}
    def call(operation,value):
        if operation not in paths:raise ValueError('unknown native reporting route')
        connection=(http.client.HTTPSConnection if parsed.scheme=='https' else http.client.HTTPConnection)(parsed.hostname,parsed.port,timeout=5)
        try:
            connection.request('POST',paths[operation],body=local('native_handoff').encoded(value),headers={
                'Content-Type':'application/json','Authorization':'Bearer '+token.decode()})
            response=connection.getresponse();raw=response.read(32769)
            if response.status!=200 or len(raw)>32768:raise ValueError('native reporting admission unconfirmed')
            return local('capture_intake').local('contract').decode(raw)
        finally:connection.close()
    return call


class Adapter:
    def __init__(self,configuration,*,call=None,actual=None):
        required={'contract','policy','scope','contexts','queue','origin','token_file'}
        if type(configuration) is not dict or set(configuration)!=required or configuration['contract']!='hermes-native-reporting.v1':
            raise ValueError('exact installed native reporting configuration required')
        self.config=configuration;self.native=local('native_handoff');self.policy=self.native.policy(configuration['policy'])
        if set(configuration['contexts'])!=set(self.policy['issues']):raise ValueError('exact configured engineering contexts required')
        self.intake=local('capture_intake');self.c=self.intake.local('contract');self.contract=self.intake.local('reporting_contract')
        for issue,ctx in configuration['contexts'].items():
            pin=self.policy['issues'][issue]
            if (ctx.get('work') is None or ctx['project_id']!=pin['project_id'] or ctx['work']['work_item_id']!=pin['work_id'] or
                    ctx['work']['work_revision_sha256']!=pin['work_revision_sha256'] or ctx['architecture']['version']!=pin['architecture_version'] or
                    ctx['architecture']['markdown_sha256']!=pin['architecture_sha256']):raise ValueError('native reporting pins differ')
            self.contract.validate(self.report(issue,'checkpoint.report',dict(report_id='rpt_'+'0'*32,attempt_id=None,observations=[],
                alternatives_and_reasons=[],changes=[],validation=[],open_questions=[],next_step='Installed configuration check only.',references=[]),'configuration',None))
        self.queue=local('runtime_handoff').Queue(configuration['queue']);self.actual=actual or local('hermes_native_context').actual
        if call is None:
            call=transport(configuration['origin'],local('protected_config').read(configuration['token_file'],maximum=257).strip())
        self.call=call

    def report(self,issue,operation,body,key,run):
        return dict(contract='engineering-reporting.v1',operation=operation,client_event_key='hermes-native:'+key,
            expected_head=None,scope=self.config['scope'],context=self.config['contexts'][issue],
            source=dict(kind='agent_reported',namespace='hermes_runtime_adapter',id=run),occurred_at=None,body=body)

    def record(self,operation,arguments):
        Draft202012Validator(schema(operation)).validate(arguments)
        native=self.actual()
        if local('hermes_native_context').parse('api_server',native['hermes_session_id'],native['run_id'])!=native:
            raise ValueError('actual native source differs')
        if native['organization_id']!=self.policy['organization_id']:raise ValueError('actual native organization differs')
        clean,_=self.intake.redact_object(arguments)
        if len(self.c.encoded(clean))>24000:raise ValueError('bounded checkpoint/handoff prose required; retain full source separately')
        identity=dict(native=native,operation=operation,key=clean['key'])
        frame=dict(contract='hermes-native-tool-report.v1',id=self.native.stable_uuid(identity),native=native,operation=operation,arguments=clean)
        result=self.queue.stage(frame)
        return dict(result,source='agent_reported',work_context='pending_retained_run_resolution',authority_granted=False)

    def deliver(self,frame):
        if (type(frame) is not dict or set(frame)!={'contract','id','native','operation','arguments'} or frame['contract']!='hermes-native-tool-report.v1'):
            raise ValueError('exact frozen native report required')
        n=frame['native'];self.native.identifier(frame['id'])
        parsed=local('hermes_native_context').parse('api_server',n['hermes_session_id'],n['run_id'])
        if parsed!=n or n['organization_id']!=self.policy['organization_id']:raise ValueError('frozen native source differs')
        Draft202012Validator(schema(frame['operation'])).validate(frame['arguments'])
        if frame['id']!=self.native.stable_uuid(dict(native=n,operation=frame['operation'],key=frame['arguments']['key'])):
            raise ValueError('frozen native report identity differs')
        reply=self.call('context',dict(contract='jarvis-native-context.v1',**n))
        if type(reply) is not dict:raise ValueError('bounded native context reply required')
        ctx=reply.get('context')
        if (reply.get('execution_started') is not False or type(ctx) is not dict or
                set(ctx)!={'session_id','issue_id','binding','parent_handoff_id','depth','delivery_id'} or
                ctx['session_id']!=n['session_id'] or ctx['binding']!=self.policy['issues'].get(ctx['issue_id'])):
            raise ValueError('exact retained native engineering run unavailable')
        self.native.identifier(ctx['delivery_id'])
        if frame['operation']=='handoff':
            intent=self.native.prepare(self.policy,'jarvis',{k:v for k,v in ctx.items() if k!='delivery_id'},frame['arguments'])
            ack=self.call('handoff',intent)
            if ack!=dict(staged=True,request_id=intent['id'],execution_started=False):raise ValueError('native handoff admission unconfirmed')
        else:
            args=frame['arguments'];identity=frame['id']
            body={k:args.get(k,[]) for k in ('observations','alternatives_and_reasons','changes','validation','open_questions','references')}
            # The passive lifecycle importer derives this same attempt from the
            # retained run. Source binding must be staged before its checkpoint.
            aid=local('runtime_reporting').ident('att_','hermes-runtime:'+self.policy['organization_id']+':'+self.policy['agents']['jarvis']+':'+ctx['delivery_id'])
            body.update(report_id=local('runtime_reporting').ident('rpt_','hermes-checkpoint:'+identity),attempt_id=aid,next_step=args['next_step'])
            request=self.contract.validate(self.report(ctx['issue_id'],'checkpoint.report',body,identity,n['run_id']))
            ack=self.call('checkpoint',dict(id=frame['id'],native=n,report=request))
            if ack!=dict(staged=True,request_id=frame['id'],execution_started=False):raise ValueError('native checkpoint admission unconfirmed')
        return dict(staged=True,request_id=frame['id'],execution_started=False)

    def flush(self):
        # Multiple Hermes processes and tool calls may attempt recovery at once.
        # Serialize the entire network/receipt operation, including across processes.
        self.intake.private(self.queue.path,True)
        path=self.queue.path/'delivery.lock'
        fd=os.open(path,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
        try:
            self.intake.private(path)
            fcntl.flock(fd,fcntl.LOCK_EX)
            return self.queue.flush(self.deliver,independent=True)
        finally:
            os.close(fd)


def start_delivery_worker(configuration_path,*,interval=60,stop=None):
    """Retry retained reports without launching an agent or requiring a tool call."""
    if type(interval) not in (int,float) or not 1<=interval<=3600:
        raise ValueError('bounded passive delivery interval required')
    stop=stop or threading.Event()
    def run():
        while not stop.wait(interval):
            try:
                Adapter(local('protected_config').decode(configuration_path,maximum=1024*1024)).flush()
            except Exception:
                # No report content, tokens, or exception text in shared logs.
                logging.getLogger(__name__).warning('Native reporting delivery remains pending or unavailable')
    thread=threading.Thread(target=run,name='engineering-reporting-delivery',daemon=True)
    thread.start()
    return stop,thread


def register(ctx,configuration_path):
    """Native plugin wrapper passes an installed path; tool arguments cannot."""
    def handle(operation,arguments):
        try:
            adapter=Adapter(local('protected_config').decode(configuration_path,maximum=1024*1024))
            result=adapter.record(operation,arguments)
            # Failure leaves the original local request pending. No model or
            # engineering run is launched to repair reporting delivery.
            try:result['delivery']=adapter.flush()
            except (ValueError,OSError,http.client.HTTPException):result['delivery']=dict(pending=True)
            return json.dumps(result)
        except Exception:
            return json.dumps(dict(error='Native engineering report refused or unconfirmed; retain the stable key and source context.',execution_started=False))
    for operation in ('checkpoint','handoff'):
        name='engineering_'+operation
        ctx.register_tool(name=name,toolset='engineering_reporting',schema=dict(name=name,
            description='Record a meaningful checkpoint for this exact native engineering run.' if operation=='checkpoint' else
                'Request Codex engineering help on the same mapped work and architecture; no approval or execution authority is granted.',
            parameters=schema(operation)),handler=lambda arguments,_operation=operation,**kwargs:handle(_operation,arguments))
