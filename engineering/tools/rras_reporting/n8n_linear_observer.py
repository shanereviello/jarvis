"""Inactive selected-project reader; n8n keeps its existing OAuth credential.

This private, header-authenticated read endpoint accepts only operation/object/
cursor parameters and builds the GraphQL query itself. No model, mutation,
arbitrary query/URL, provider environment or private-history mount is involved.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import uuid
spec=importlib.util.spec_from_file_location('n8n_observer_source',Path(__file__).with_name('linear_observer.py'))
observer=importlib.util.module_from_spec(spec);spec.loader.exec_module(observer)


def configuration(value):
    if type(value) is not dict or set(value)!={'contract','organization_id','team_id','actor_id','project_id','credentials'}:
        raise ValueError('exact selected reader policy required')
    if value['contract']!='engineering-linear-reader.v1':raise ValueError('reader contract differs')
    for k in ('organization_id','team_id','actor_id','project_id'):observer.identifier(value[k])
    credentials=value['credentials']
    if (type(credentials) is not dict or set(credentials)!={'oauth','reader_header'} or
            any(type(x) is not str or not 1<=len(x)<=128 for x in credentials.values()) or
            credentials['oauth']==credentials['reader_header']):raise ValueError('distinct existing credential references required')
    return value


def scripts(value):
    value=configuration(value);policy={k:value[k] for k in ('organization_id','team_id','actor_id','project_id')}
    prefix='const policy='+json.dumps(policy)+';\n'
    prepare=prefix+'const queries='+json.dumps(observer.QUERIES)+''';
const body=$json.body;
if (!body || typeof body !== 'object' || Array.isArray(body) ||
    Object.keys(body).sort().join(',') !== 'after,object_id,operation' ||
    !Object.hasOwn(queries,body.operation) || typeof body.object_id !== 'string' ||
    !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(body.object_id) ||
    !(body.after === null || (typeof body.after === 'string' && body.after.length > 0 && body.after.length <= 512))) {
  throw new Error('bounded exact selected read required');
}
if (body.operation !== 'comments' && body.object_id !== policy.project_id) throw new Error('unselected project');
if (body.operation === 'project' && body.after !== null) throw new Error('project has no page cursor');
const variables={id:policy.project_id};
if (body.operation !== 'project') variables.after=body.after;
return [{json:{operation:body.operation,object_id:body.object_id,
  graphql:{query:queries[body.operation].replace('ISSUE_UUID',body.object_id),variables}}}];
'''
    validate=prefix+'''
const source=$('Prepare selected Linear read').first().json;
if ($json.errors?.length || !$json.data) throw new Error('Linear read incomplete');
const data=$json.data;
if (data.viewer?.id !== policy.actor_id || data.viewer?.organization?.id !== policy.organization_id ||
    data.project?.id !== policy.project_id) throw new Error('selected reader identity differs');
let connection;
if (source.operation === 'comments') {
  const issues=data.project.issues?.nodes;
  if (!Array.isArray(issues) || issues.length !== 1 || issues[0].id !== source.object_id ||
      issues[0].project?.id !== policy.project_id || issues[0].team?.id !== policy.team_id) throw new Error('selected issue unavailable');
  connection=issues[0].comments;
} else if (source.operation !== 'project') connection=data.project[source.operation];
if (connection) {
  if (!Array.isArray(connection.nodes) || connection.nodes.length > 50 ||
      typeof connection.pageInfo?.hasNextPage !== 'boolean') throw new Error('bounded native page required');
  if (source.operation === 'issues' && connection.nodes.some(x => x.project?.id !== policy.project_id || x.team?.id !== policy.team_id)) throw new Error('unselected issue');
} else if (source.operation !== 'project') throw new Error('page unavailable');
return [{json:{data}}];
'''
    return prepare,validate


def render(value):
    value=configuration(value);prepare,validate=scripts(value)
    def node(name,type_,version,parameters,x,credentials=None):
        result=dict(id=str(uuid.uuid5(uuid.NAMESPACE_URL,'shrr-linear-reader:'+value['project_id']+':'+name)),
            name=name,type='n8n-nodes-base.'+type_,typeVersion=version,position=[x,0],parameters=parameters,retryOnFail=False)
        if type_=='webhook':result['webhookId']=result['id']
        if credentials:result['credentials']=credentials
        return result
    nodes=[node('Private selected Linear read','webhook',2,dict(httpMethod='POST',
        path='rras-history-linear-read-'+value['project_id'],authentication='headerAuth',responseMode='lastNode',options={}),0,
        dict(httpHeaderAuth=dict(id=value['credentials']['reader_header'],name='History observer read bridge'))),
        node('Prepare selected Linear read','code',2,dict(jsCode=prepare),240),
        node('Read selected Linear page','httpRequest',4.2,dict(method='POST',url='https://api.linear.app/graphql',
            authentication='genericCredentialType',genericAuthType='oAuth2Api',sendBody=True,contentType='raw',rawContentType='application/json',
            body='={{ JSON.stringify($json.graphql) }}',options=dict(timeout=15000)),480,
            dict(oAuth2Api=dict(id=value['credentials']['oauth'],name='Selected native Linear OAuth'))),
        node('Validate selected Linear read','code',2,dict(jsCode=validate),720)]
    connections={a['name']:dict(main=[[dict(node=b['name'],type='main',index=0)]]) for a,b in zip(nodes,nodes[1:])}
    return dict(id=uuid.uuid5(uuid.NAMESPACE_URL,'shrr-linear-reader:'+value['project_id']).hex[:16],
        name='RRAS Selected Linear History Reader '+value['project_id'],active=False,nodes=nodes,connections=connections,
        settings=dict(executionOrder='v1',saveDataErrorExecution='none',saveDataSuccessExecution='none',saveManualExecutions=False,
            executionTimeout=30),pinData={},tags=[])


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    value=render(json.loads(args.config.read_bytes()));args.output.write_text(json.dumps(value,indent=2)+'\n');args.output.chmod(0o600)


if __name__=='__main__':main()
