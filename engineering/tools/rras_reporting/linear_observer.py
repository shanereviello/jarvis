"""Passive selected-project GraphQL reader. Never mutates Linear or launches work.

The supplied query transport owns authentication (n8n OAuth in production).
Objects are explicit snapshots, not approval/execution instructions. Every pass
starts from page one, tolerates overlap and preserves frozen delivery requests.
"""
import importlib.util
from pathlib import Path
import uuid


def local(name):
    spec=importlib.util.spec_from_file_location('linear_observer_'+name,Path(__file__).with_name(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


PAGE='pageInfo { hasNextPage endCursor }'
QUERIES=dict(
    project='query ObserveProject($id:String!){ viewer { id organization { id } } project(id:$id){ id name description updatedAt url } }',
    issues='query ObserveIssues($id:String!,$after:String){ viewer { id organization { id } } project(id:$id){ id issues(first:50,after:$after){ nodes { id identifier title description updatedAt url team { id } project { id } state { id name } assignee { id name } } '+PAGE+' } } }',
    comments='query ObserveComments($id:String!,$after:String){ viewer { id organization { id } } project(id:$id){ id issues(first:1,filter:{id:{eq:"ISSUE_UUID"}}){nodes { id team { id } project { id } comments(first:50,after:$after){ nodes { id body updatedAt user { id name } } '+PAGE+' } } } } }',
    documents='query ObserveDocuments($id:String!,$after:String){ viewer { id organization { id } } project(id:$id){ id documents(first:50,after:$after){ nodes { id title content updatedAt } '+PAGE+' } } }')


def identifier(value):
    if type(value) is not str or str(uuid.UUID(value))!=value:raise ValueError('canonical native UUID required')
    return value


def configuration(value):
    if type(value) is not dict or set(value)!={'organization_id','team_id','actor_id','project_id','scope','context','issues'}:
        raise ValueError('exact selected observer binding required')
    for k in ('organization_id','team_id','actor_id','project_id'):identifier(value[k])
    if type(value['issues']) is not dict or len(value['issues'])>1000:raise ValueError('bounded explicit issue mappings required')
    rc=local('capture_intake').local('reporting_contract')
    for ctx in [value['context']]+list(value['issues'].values()):
        rc.validate(dict(contract='engineering-reporting.v1',operation='source.observe',client_event_key='observer-config',
            expected_head=None,scope=value['scope'],context=ctx,source=dict(kind='imported',namespace='linear_poll',id=value['project_id']),
            occurred_at=None,body=dict(source=dict(namespace='linear_project',id=value['project_id']),source_observed_at=None,
                cursor=None,status='unknown',gaps=[],detail='Configuration validation only.')))
    if value['context'] is None or value['context']['work'] is not None:raise ValueError('explicit project-only context required')
    for issue,ctx in value['issues'].items():
        identifier(issue)
        if ctx is not None and ctx['project_id']!=value['context']['project_id']:raise ValueError('issue crosses selected project')
    return value


def poll(spool,selected,query):
    selected=configuration(selected);source=dict(namespace='linear_project',id=selected['project_id'])
    collected=0;cursor=None;time=local('capture_collectors').source_time
    def fetch(kind,identifier_,after=None):
        identifier(identifier_)
        document=QUERIES[kind].replace('ISSUE_UUID',identifier_)
        value=query(dict(operation=kind,object_id=identifier_,query=document,variables=dict(id=selected['project_id'],**({} if kind=='project' else dict(after=after)))))
        if type(value) is not dict or value.get('errors') or type(value.get('data')) is not dict:raise ValueError('complete authenticated GraphQL response required')
        data=value['data'];viewer=data.get('viewer') or {}
        if viewer.get('id')!=selected['actor_id'] or (viewer.get('organization') or {}).get('id')!=selected['organization_id']:
            raise ValueError('observer actor/organization differs')
        return data
    def save(kind,node,context):
        nonlocal collected
        identifier(node.get('id'))
        result=spool.observe_linear(node,scope=selected['scope'],context=context,
            organization_id=selected['organization_id'],team_id=selected['team_id'],project_id=selected['project_id'],
            object_kind=kind,object_id=node['id'],updated_at=time(node.get('updatedAt')))
        collected+=int(result['staged'])
    def pages(kind,root_id):
        nonlocal cursor
        after=None;seen=set()
        for page in range(1000):
            data=fetch(kind,root_id,after);root=data.get('project')
            if type(root) is not dict or root.get('id')!=selected['project_id']:raise ValueError('selected parent differs')
            if kind=='comments':
                issues=(root.get('issues') or {}).get('nodes')
                if type(issues) is not list or len(issues)!=1 or issues[0].get('id')!=root_id:raise ValueError('selected issue unavailable')
                root=issues[0]
            if kind=='comments' and ((root.get('project') or {}).get('id')!=selected['project_id'] or
                    (root.get('team') or {}).get('id')!=selected['team_id']):raise ValueError('comment source crosses selected project/team')
            connection=root.get(kind);info=(connection or {}).get('pageInfo') or {};nodes=(connection or {}).get('nodes')
            if type(nodes) is not list or len(nodes)>50 or type(info.get('hasNextPage')) is not bool:raise ValueError('bounded native page required')
            for node in nodes:
                if type(node) is not dict:raise ValueError('native object required')
                yield node
            cursor=info.get('endCursor')
            if not info['hasNextPage']:return
            if type(cursor) is not str or not cursor or len(cursor)>512 or cursor in seen or not nodes:
                raise ValueError('advancing bounded native cursor required')
            seen.add(cursor);after=cursor
        raise ValueError('observer page bound reached; coverage incomplete')
    try:
        data=fetch('project',selected['project_id']);project=data.get('project')
        if type(project) is not dict or project.get('id')!=selected['project_id']:raise ValueError('selected project unavailable')
        save('project',project,selected['context'])
        # Include unmapped new issues as unmapped observations. Do not infer work
        # from repository, labels, title similarity or imported text.
        seen_issues=set()
        for issue in pages('issues',selected['project_id']):
            if ((issue.get('project') or {}).get('id')!=selected['project_id'] or
                    (issue.get('team') or {}).get('id')!=selected['team_id']):raise ValueError('issue crosses selected project/team')
            context=selected['issues'].get(issue['id']);save('issue',issue,context)
            if issue['id'] in seen_issues:continue
            seen_issues.add(issue['id'])
            for comment in pages('comments',issue['id']):save('comment',dict(comment,observed_issue_id=issue['id']),context)
        for document in pages('documents',selected['project_id']):save('document',document,selected['context'])
        spool.source_status(scope=selected['scope'],context=selected['context'],session=source,status='current',
            detail='Selected project poll completed; intermediate edits and between-poll deletions may be absent.',
            cursor=cursor,source_observed_at=local('capture_intake').stamp())
        return dict(observed=collected,complete_pass=True,work_launched=False)
    except (ValueError,OSError,TypeError,KeyError):
        try:spool.source_status(scope=selected['scope'],context=selected['context'],session=source,status='gap',
            detail='Selected project poll incomplete; frozen observations retained, no assignment or approval inferred.',cursor=None)
        except (ValueError,OSError):pass
        return dict(observed=collected,complete_pass=False,work_launched=False)
