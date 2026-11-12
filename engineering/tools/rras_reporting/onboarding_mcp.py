"""Planning-only MCP tools backed by a kernel-authenticated local broker."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import stat
import time
from jsonschema import Draft202012Validator, ValidationError


def local(name):
    spec=importlib.util.spec_from_file_location('onboarding_mcp_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


TEXT={'type':'string','minLength':1,'maxLength':16384}
DRAFT={'type':'object','additionalProperties':False,'required':['name','overview','intended_outcome','in_scope','out_of_scope','markdown','plan_ids'],
       'properties':dict(name={'type':'string','minLength':1,'maxLength':180},overview=TEXT,intended_outcome=TEXT,in_scope=TEXT,out_of_scope=TEXT,
            markdown={'type':'string','minLength':1,'maxLength':90000},plan_ids={'type':'array','minItems':1,'maxItems':128,'uniqueItems':True,
            'items':{'type':'string','pattern':'^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$'}})}
WORK={'type':'object','additionalProperties':False,'required':['plan_id','title','objective','rationale','allowed_paths','acceptance_criteria'],
      'properties':dict(plan_id={'type':'string','pattern':'^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$'},title={'type':'string','minLength':1,'maxLength':200},
          objective=TEXT,rationale=TEXT,allowed_paths={'type':'array','maxItems':128,'items':TEXT},
          acceptance_criteria={'type':'array','maxItems':128,'items':{'type':'object','additionalProperties':False,'required':['id','description'],
          'properties':{'id':{'type':'string','minLength':1,'maxLength':128},'description':TEXT}}})}
SCHEMAS={
 'engineering_draft_project':{'type':'object','additionalProperties':False,'required':['proposal'],'properties':{'proposal':DRAFT}},
 'engineering_draft_work':{'type':'object','additionalProperties':False,'required':['issue_id','proposal'],
     'properties':{'issue_id':{'type':'string','pattern':'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'},'proposal':WORK}},
}


class Launch:
    """Construct the tool configuration from trusted runtime state only."""
    def __init__(self,path,service_uid,python):
        self.unix=local('onboarding_broker_unix').unix();self.unix.uid(service_uid)
        self.path=self.unix.endpoint(path);self.service_uid=service_uid;self.python=Path(python)
        info=self.python.stat()
        if (not self.python.is_absolute() or not stat.S_ISREG(info.st_mode) or
                info.st_uid not in (0,os.getuid()) or info.st_mode&0o022 or not os.access(self.python,os.X_OK)):
            raise ValueError('trusted installed MCP Python required')

    def parameters(self,dispatch):
        local('onboarding_drafts').identifier(dispatch)
        tools=list(SCHEMAS)
        return dict(config={'mcp_servers':{'engineering_planning':dict(command=str(self.python),
            args=['-I','-B',str(Path(__file__).resolve()),'--socket',str(self.path),'--service-uid',str(self.service_uid),'--dispatch',dispatch],
            enabled=True,required=True,enabled_tools=tools,startup_timeout_sec=15,tool_timeout_sec=30,
            tools={name:{'approval_mode':'approve'} for name in tools})}},
            developerInstructions=('Planning only: retain the proposed architecture with engineering_draft_project, '
                'then link independently verified existing Linear issues with engineering_draft_work. '
                'The tools do not approve the architecture or authorize implementation. '
                'Do not modify a production repository or claim approval from an agent message.'))

    def verify_inventory(self,client,thread):
        for attempt in range(10):
            result=client.call('mcpServerStatus/list',dict(threadId=thread,detail='toolsAndAuthOnly',limit=100))
            if type(result) is not dict or result.get('nextCursor') is not None or type(result.get('data')) is not list:
                raise ValueError('bounded complete planning MCP inventory required')
            active=[item for item in result['data'] if item.get('runtimeStatus')!='disabled']
            if any(item.get('name')!='engineering_planning' or set(item.get('tools',{}))-set(SCHEMAS) for item in active):
                raise ValueError('unexpected planning MCP inventory')
            if len(active)==1 and set(active[0].get('tools',{}))==set(SCHEMAS):return True
            if attempt<9:time.sleep(.2)
        raise ValueError('exact planning MCP inventory unavailable')


class Client:
    def __init__(self,path,service_uid,dispatch):
        self.unix=local('onboarding_broker_unix').unix();self.unix.uid(service_uid)
        self.path=self.unix.endpoint(path);self.service_uid=service_uid
        self.dispatch=local('onboarding_drafts').identifier(dispatch)

    def call(self,name,arguments):
        if name not in SCHEMAS:raise ValueError('unknown planning tool')
        Draft202012Validator(SCHEMAS[name]).validate(arguments)
        request={'operation':'draft.project' if name=='engineering_draft_project' else 'draft.work',
                 'dispatch_id':self.dispatch,'proposal':arguments['proposal']}
        if name=='engineering_draft_work':request['issue_id']=arguments['issue_id']
        return self.unix.call(self.path,self.service_uid,request)


def server(client):
    os.environ.clear();os.environ.update(PATH='/usr/bin:/bin',HOME='/nonexistent',LANG='C.UTF-8')
    descriptions={'engineering_draft_project':'Retain the exact unapproved project architecture draft. This does not approve or authorize work.',
                  'engineering_draft_work':'Link an independently verified Linear issue to a proposed draft work item. This does not authorize execution.'}
    tools=[dict(name=name,description=descriptions[name],inputSchema=schema) for name,schema in SCHEMAS.items()]
    error='Draft request refused or uncertain. Preserve the planning identity and reconcile; no execution is authorized.'
    from importlib.metadata import version
    major=int(version('mcp').split('.')[0])
    import anyio
    import mcp.types as types
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    if major==1:
        instance=Server('rras-planning-drafts')
        @instance.list_tools()
        async def listing():return [types.Tool(**item) for item in tools]
        @instance.call_tool()
        async def call(name,arguments):
            try:return [types.TextContent(type='text',text=json.dumps(client.call(name,arguments)))]
            except (ValueError,KeyError,TypeError,OSError,sqlite3.Error,ValidationError):raise ValueError(error) from None
    elif major==2:
        async def listing(context,params):return types.ListToolsResult(tools=[types.Tool(**item) for item in tools])
        async def call(context,params):
            try:return types.CallToolResult(content=[types.TextContent(type='text',text=json.dumps(client.call(params.name,params.arguments or {})))])
            except (ValueError,KeyError,TypeError,OSError,sqlite3.Error,ValidationError):
                return types.CallToolResult(isError=True,content=[types.TextContent(type='text',text=error)])
        instance=Server('rras-planning-drafts',on_list_tools=listing,on_call_tool=call)
    else:raise ValueError('unreviewed MCP version')
    async def run():
        async with stdio_server() as (read,write):await instance.run(read,write,instance.create_initialization_options())
    anyio.run(run)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--socket',required=True);parser.add_argument('--service-uid',type=int,required=True);parser.add_argument('--dispatch',required=True)
    args=parser.parse_args()
    try:server(Client(args.socket,args.service_uid,args.dispatch))
    except (ValueError,KeyError,TypeError,OSError,sqlite3.Error,ValidationError):parser.exit(1,'Planning tool refused.\n')


if __name__=='__main__':main()
