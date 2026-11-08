"""One scoped checkpoint tool for a configured Codex runtime session.

No Linear credential, work selector, private-history read, execution, approval or
publication tool is exposed. The parent runtime journal supplies actual context;
agent text supplies attributed observations, never new authority.
"""
import argparse
from contextlib import contextmanager
import importlib.util
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys
from jsonschema import Draft202012Validator,ValidationError


def local(name):
    spec=importlib.util.spec_from_file_location('runtime_checkpoint_'+name,Path(__file__).with_name(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def checkpoint_schema():
    rc=local('capture_intake').local('reporting_contract');body=rc.DEFS['report']
    return dict(type='object',properties=dict(key=rc.NAME,**{k:v for k,v in body['properties'].items() if k not in ('report_id','attempt_id')}),
        required=['key','observations','next_step'],additionalProperties=False,**{'$defs':rc.DEFS})


class Launch:
    """Trusted thread configuration; never constructed from an agent argument."""
    def __init__(self,state,configuration,python):
        runtime=local('codex_runtime');self.state=runtime.private(state,True)
        self.configuration=runtime.private(configuration);self.python=Path(python)
        info=self.python.stat()
        if (not self.python.is_absolute() or not stat.S_ISREG(info.st_mode) or info.st_uid not in (0,os.getuid()) or
                info.st_mode&0o022 or not os.access(self.python,os.X_OK)):raise ValueError('trusted installed MCP Python required')

    def arguments(self,session,dispatch=None):
        return ['-I','-B',str(Path(__file__).resolve()),'--state',str(self.state),'--reporting-policy',str(self.configuration),'--session',session]

    def names(self):return ['engineering_checkpoint']+(['engineering_handoff'] if getattr(self,'handoff_enabled',False) else [])

    def parameters(self,session,dispatch=None):
        local('codex_runtime').identifier(session)
        tool=dict(command=str(self.python),args=self.arguments(session,dispatch),enabled=True,required=False,
            enabled_tools=self.names(),startup_timeout_sec=15,tool_timeout_sec=15)
        return dict(config=dict(mcp_servers=dict(engineering_checkpoint=tool)),developerInstructions=(
            'Use engineering_checkpoint at meaningful findings, choices, failed attempts, changes, validation and pauses. '
            'Use a stable distinct key per checkpoint. Report observations, reasons, evidence and next steps; '
            'do not log every command. The trusted tool supplies this turn\'s exact work/architecture context. '
            'Checkpoint delivery is passive: preserve failures and continue authorized work without rerunning it. '
            'This tool grants no execution, spending, acceptance, approval, merge or deployment authority.'+
            (' Use engineering_handoff to request Jarvis assistant context or follow-up using a stable key. '
             'It retains the same work and architecture. Staging does not transfer engineering ownership or interrupt this turn; '
             'finish or pause safely, then the transport waits for actual source quiescence before publication. '
             'Do not wait in a reply loop or treat advice as a new execution approval.' if getattr(self,'handoff_enabled',False) else '')))

    def verify_inventory(self,client,thread):
        value=client.call('mcpServerStatus/list',dict(threadId=thread,detail='toolsAndAuthOnly',limit=100))
        if type(value) is not dict or value.get('nextCursor') is not None or type(value.get('data')) is not list:
            raise ValueError('bounded complete runtime MCP inventory required')
        for server in value['data']:
            if server.get('runtimeStatus')=='disabled':continue
            if server.get('name')!='engineering_checkpoint':raise ValueError('unexpected MCP identity in coding runtime')
            if set(server.get('tools',{})) - set(self.names()):raise ValueError('unexpected runtime recorder tool')
        # No model call is needed for discovery. Missing recorder is a reporting
        # gap; an extra MCP identity is an authority error and refuses dispatch.
        return any(s.get('name')=='engineering_checkpoint' and set(self.names())<=set(s.get('tools',{})) for s in value['data'])


class Checkpoints:
    def __init__(self,state,configuration,session):
        runtime=local('codex_runtime');runtime.identifier(session);self.session=session
        self.state=runtime.private(state,True);self.path=runtime.private(self.state/'runtime.sqlite3');self.r=local('runtime_reporting')
        self.c=self.r.local('capture_intake').local('contract')
        with self.connection() as db:self.policy=runtime.policy(self.c.decode(db.execute('SELECT body FROM policy').fetchone()[0]))
        self.reporter=self.r.Reporter(configuration,self.policy)

    @contextmanager
    def connection(self):
        local('codex_runtime').private(self.path)
        db=sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True,timeout=3);db.row_factory=sqlite3.Row
        db.execute('PRAGMA trusted_schema=OFF');db.execute('PRAGMA query_only=ON')
        try:yield db
        finally:db.close()

    def schema(self):
        return checkpoint_schema()

    def record(self,arguments):
        Draft202012Validator(self.schema()).validate(arguments)
        with self.connection() as db:
            rows=db.execute("SELECT * FROM turns WHERE session=? AND state IN ('preparing','running','uncertain','interrupt_requested')",(self.session,)).fetchall()
        if len(rows)!=1:raise ValueError('one active configured runtime session required')
        row=rows[0]
        if self.c.digest(row['request'])!=row['digest']:raise ValueError('frozen runtime request differs')
        native=self.c.decode(row['request']);pin=self.policy['issues'].get(row['issue'])
        if (native['session_id']!=self.session or native['issue_id']!=row['issue'] or native['binding']!=pin or
                native['organization_id']!=self.policy['organization_id'] or native['app_user_id']!=self.policy['app_user_id']):
            raise ValueError('actual runtime issue/app binding differs')
        aid=self.r.ident('att_','codex-runtime:'+self.policy['organization_id']+':'+self.policy['app_user_id']+':'+row['dispatch'])
        body={k:arguments.get(k,[]) for k in ('observations','alternatives_and_reasons','changes','validation','open_questions','references')}
        body.update(report_id=self.r.ident('rpt_','runtime-agent-checkpoint:'+row['dispatch']+':'+arguments['key']),attempt_id=aid,next_step=arguments['next_step'])
        body,redactions=self.reporter.intake.redact_object(body)
        request=self.reporter.request(row,'checkpoint.report',body,key='runtime-agent-checkpoint:'+self.c.digest(self.c.encoded(
            dict(dispatch=row['dispatch'],key=arguments['key']))))
        with self.reporter.spool.connection() as db:
            db.execute('BEGIN IMMEDIATE');sequence=self.reporter.append(db,request);db.commit()
        self.reporter.intake.sync(self.reporter.spool.root)
        return dict(staged=True,sequence=sequence,source='agent_reported',project_id=request['context']['project_id'],
            work_item_id=request['context']['work']['work_item_id'],architecture_version=request['context']['architecture']['version'],
            history_delivery='pending_or_replayed',redactions=redactions,authority_granted=False)


class BrokerLaunch(Launch):
    """Native account receives only an endpoint and public service UID."""
    def __init__(self,socket_path,service_uid,python,*,handoff=False):
        if type(handoff) is not bool:raise ValueError('explicit installed handoff selection required')
        self.handoff_enabled=handoff
        runtime=local('codex_runtime');u=runtime.history_unix();u.uid(service_uid)
        self.socket=u.endpoint(socket_path);self.service_uid=service_uid;self.python=Path(python)
        info=self.python.stat()
        if not self.python.is_absolute() or not stat.S_ISREG(info.st_mode) or info.st_uid not in (0,os.getuid()) or info.st_mode&0o022:
            raise ValueError('trusted installed MCP Python required')

    def arguments(self,session,dispatch=None):
        local('codex_runtime').identifier(dispatch)
        return ['-I','-B',str(Path(__file__).resolve()),
            '--socket',str(self.socket),'--service-uid',str(self.service_uid)]+(['--handoff'] if self.handoff_enabled else [])+['--session',session,'--dispatch',dispatch]


class BrokerClient:
    def __init__(self,path,service_uid,session,dispatch,*,handoff=False):
        self.handoff_enabled=handoff
        self.u=local('codex_runtime').history_unix();self.u.uid(service_uid)
        self.path=self.u.endpoint(path);self.service_uid=service_uid
        local('codex_runtime').identifier(session);local('codex_runtime').identifier(dispatch)
        self.session=session;self.dispatch=dispatch

    def schema(self):return checkpoint_schema()

    def record(self,arguments):
        Draft202012Validator(self.schema()).validate(arguments)
        return self.u.call(self.path,self.service_uid,dict(method='checkpoint',session_id=self.session,dispatch_id=self.dispatch,arguments=arguments))

    def handoff(self,arguments):
        if not self.handoff_enabled:raise ValueError('installed handoff tool required')
        Draft202012Validator(local('runtime_handoff').schema()).validate(arguments)
        return self.u.call(self.path,self.service_uid,dict(method='handoff',session_id=self.session,dispatch_id=self.dispatch,arguments=arguments))


def server(checkpoints):
    # MCP runs as the configured local recorder, not with provider/Linear auth.
    os.environ.clear();os.environ.update(PATH='/usr/bin:/bin',HOME='/nonexistent',LANG='C.UTF-8')
    name='engineering_checkpoint';error='Checkpoint refused or unconfirmed; retain the stable key and known work context. No work was launched.'
    tools=[dict(name=name,description='Record a meaningful checkpoint for this exact configured runtime work; no execution or approval authority.',inputSchema=checkpoints.schema())]
    if getattr(checkpoints,'handoff_enabled',False):tools.append(dict(name='engineering_handoff',
        description='Stage a bounded handoff to Jarvis for this exact work. Grants no coding ownership or execution authority; publication waits for source quiescence.',inputSchema=local('runtime_handoff').schema()))
    def invoke(tool,arguments):
        if tool==name:return checkpoints.record(arguments)
        if tool=='engineering_handoff' and getattr(checkpoints,'handoff_enabled',False):return checkpoints.handoff(arguments)
        raise ValueError('unknown tool')
    from importlib.metadata import version
    major=int(version('mcp').split('.')[0])
    if major==1:
        from mcp.server import Server
        import mcp.types as types
        instance=Server('rras-runtime-engineering-checkpoints')
        @instance.list_tools()
        async def listing():return [types.Tool(**item) for item in tools]
        @instance.call_tool()
        async def call(tool,arguments):
            try:
                value=invoke(tool,arguments)
                return [types.TextContent(type='text',text=json.dumps(value))]
            except (ValueError,KeyError,TypeError,OSError,sqlite3.Error,ValidationError):raise ValueError(error) from None
        import anyio
        from mcp.server.stdio import stdio_server
        class Stdio:
            def run(self):
                async def serve():
                    async with stdio_server() as (read,write):await instance.run(read,write,instance.create_initialization_options())
                anyio.run(serve)
        return Stdio()
    if major!=2:raise ValueError('unreviewed MCP version')
    import anyio
    import mcp.types as types
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    async def listing(context,params):return types.ListToolsResult(tools=[types.Tool(**item) for item in tools])
    async def call(context,params):
        try:
            value=invoke(params.name,params.arguments or {})
            return types.CallToolResult(content=[types.TextContent(type='text',text=json.dumps(value))])
        except (ValueError,KeyError,TypeError,OSError,sqlite3.Error,ValidationError):
            return types.CallToolResult(isError=True,content=[types.TextContent(type='text',text=error)])
    instance=Server('rras-runtime-engineering-checkpoints',on_list_tools=listing,on_call_tool=call)
    class Stdio:
        def run(self):
            async def serve():
                async with stdio_server() as (read,write):await instance.run(read,write,instance.create_initialization_options())
            anyio.run(serve)
    return Stdio()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--state')
    parser.add_argument('--reporting-policy');parser.add_argument('--session');parser.add_argument('--dispatch');parser.add_argument('--socket');parser.add_argument('--service-uid',type=int)
    parser.add_argument('--handoff',action='store_true');args=parser.parse_args()
    runtime=local('codex_runtime')
    try:
        if args.socket:
            if args.state or args.reporting_policy or not args.session or not args.dispatch or args.service_uid is None:raise ValueError('exact broker-only configuration required')
            checkpoints=BrokerClient(args.socket,args.service_uid,args.session,args.dispatch,handoff=args.handoff)
        else:
            if args.handoff or args.service_uid is not None or args.dispatch or not all((args.state,args.reporting_policy,args.session)):raise ValueError('exact isolated direct fixture configuration required')
            config=json.loads(runtime.private(args.reporting_policy).read_bytes());checkpoints=Checkpoints(args.state,config,args.session)
        server(checkpoints).run()
    except (ValueError,KeyError,TypeError,OSError,sqlite3.Error,ValidationError):parser.exit(1,'Scoped checkpoint service refused.\n')


if __name__=='__main__':main()
