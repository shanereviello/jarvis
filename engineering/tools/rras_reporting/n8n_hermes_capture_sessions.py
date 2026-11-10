"""Render an inactive, authenticated metadata reader for future sessions."""
import importlib.util
from pathlib import Path
import uuid


def render(organization_id, cutoff, postgres_reference, header_reference):
    path = Path(__file__).with_name('hermes_capture_selection.py')
    spec = importlib.util.spec_from_file_location('future_hermes_selection', path)
    selection = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(selection)
    selection.identifier(organization_id)
    selection.timestamp(cutoff)
    if (any(type(x) is not str or not x.strip() or len(x) > 128
            for x in (postgres_reference, header_reference)) or postgres_reference == header_reference):
        raise ValueError('separate database and header credential references required')
    nodes = []
    def node(name, kind, version, parameters, credential=None):
        value = dict(id=str(uuid.uuid5(uuid.NAMESPACE_URL, 'rras-hermes-future:' + organization_id + ':' + name)),
                     name=name, type='n8n-nodes-base.' + kind, typeVersion=version,
                     position=[240 * len(nodes), 0], parameters=parameters)
        if kind == 'webhook': value['webhookId'] = value['id']
        if credential:
            value['credentials'] = {credential[0]: dict(id=credential[1], name='Future Hermes reader credential reference')}
        nodes.append(value)
        return value
    node('Private future session metadata', 'webhook', 2.1,
         dict(httpMethod='POST', path='rras-hermes-future-session-metadata', responseMode='responseNode',
              authentication='headerAuth', options={}), ('httpHeaderAuth', header_reference))
    node('Validate cursor', 'code', 2, dict(mode='runOnceForAllItems', jsCode="""const b=$input.first().json.body;
const ts=/^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(?:\\.\\d{1,6})?Z$/;
const id=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
if(!b||Object.keys(b).sort().join()!=='after_id,after_time'||!ts.test(b.after_time)||!id.test(b.after_id))
 throw new Error('Exact bounded session cursor required');
return [{json:b}];"""))
    # Cutoff and organization are reviewed constants; the caller's cursor can
    # move through the result but cannot broaden the selected time or scope.
    query = f"""SELECT organization_id,agent_session_id,issue_id,hermes_session_id,
 to_char(created_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"') AS created_at
 FROM linear_bridge.agent_sessions
 WHERE organization_id='{organization_id}' AND created_at>'{cutoff}'::timestamptz
 AND (created_at,agent_session_id)>($1::timestamptz,$2::text)
 AND issue_id IS NOT NULL AND hermes_session_id IS NOT NULL
 ORDER BY created_at,agent_session_id LIMIT 4"""
    read = node('Read future session metadata', 'postgres', 2.6,
                dict(operation='executeQuery', query=query,
                     options=dict(queryReplacement='={{ [$json.after_time,$json.after_id] }}')),
                ('postgres', postgres_reference))
    read['alwaysOutputData'] = True
    node('Format bounded metadata', 'code', 2, dict(mode='runOnceForAllItems', jsCode="""const rows=$input.all().map(x=>x.json).filter(x=>x.agent_session_id!=null);
if(rows.length>4||JSON.stringify(rows).length>65536)throw new Error('Bounded metadata required');
return [{json:{contract:'hermes-future-session-page.v1',sessions:rows}}];"""))
    node('Respond with metadata', 'respondToWebhook', 1.4,
         dict(respondWith='json', responseBody='={{ $json }}', options=dict(responseCode=200)))
    connections = {a['name']: dict(main=[[dict(node=b['name'], type='main', index=0)]])
                   for a, b in zip(nodes, nodes[1:])}
    return dict(name='Future Hermes session metadata (inactive)', active=False, nodes=nodes,
                connections=connections, settings=dict(executionOrder='v1',
                saveDataErrorExecution='none', saveDataSuccessExecution='none',
                saveManualExecutions=False, executionTimeout=30), tags=[], pinData={})
