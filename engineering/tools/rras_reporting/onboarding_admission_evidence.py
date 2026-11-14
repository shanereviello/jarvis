"""Check exact admission evidence without installing policy or starting work.

The callbacks are protected operator-side readers: native Linear issue,
independent human decision attestation, and workspace isolation inspection.
The immutable history snapshot is a consistent observation, not a lock. Any
policy publisher must recheck it while holding its own admission lock.
"""
import hashlib


class Verifier:
    def __init__(self,rpc,read_issue,verify_human,verify_workspace):
        if not all(callable(f) for f in (rpc,read_issue,verify_human,verify_workspace)):
            raise ValueError('protected independent admission readers required')
        self.rpc,self.read_issue,self.verify_human,self.verify_workspace=rpc,read_issue,verify_human,verify_workspace

    def __call__(self,value):
        if type(value) is not dict:raise ValueError('exact candidate required')
        scope=value['scope'];project_id=value['project_id']
        def get(query,snapshot=None):
            query=dict(query)
            if snapshot is not None:query['snapshot']=snapshot
            return self.rpc(dict(method='project_read',scope=scope,query=query))
        project_result=get(dict(view='project',project_id=project_id))
        snapshot=project_result['snapshot'];project=project_result['project']
        if project['scope']!=scope or project['governing_version']!=value['architecture_version']:
            raise ValueError('governing architecture differs')
        documents=[x for x in project['architecture'] if x['version']==value['architecture_version'] and x['markdown_sha256']==value['architecture_sha256']]
        if len(documents)!=1:raise ValueError('governing document differs')
        document=get(dict(view='architecture',project_id=project_id,version=value['architecture_version']),snapshot)['document']
        if hashlib.sha256(document['markdown'].encode('utf-8')).hexdigest()!=value['architecture_sha256']:
            raise ValueError('governing document bytes differ')
        designation=next((x for x in reversed(project['designations']) if x['version']==value['architecture_version']),None)
        if (designation is None or designation['markdown_sha256']!=value['architecture_sha256'] or
                designation['source']!={'kind':'imported','namespace':'operator_decision','id':value['decision_receipt_sha256']}):
            raise ValueError('designation does not bind the operator decision')
        work=get(dict(view='work',work_id=value['work_id']),snapshot)
        assignment=work['assignment']
        if (work['work_revision_sha256']!=value['work_revision_sha256'] or
                work['work'].get('repository_id')!=scope['id'] or type(assignment) is not dict or
                assignment['project_id']!=project_id or assignment['architecture_version']!=value['architecture_version'] or
                assignment['assignment_sha256']!=value['assignment_sha256']):
            raise ValueError('work or assignment differs')
        def records(operation):
            offset=0;items=[]
            for _ in range(256):
                page=get(dict(view='reporting',project_id=project_id,operation=operation,limit=50,offset=offset),snapshot)
                if not page.get('available'):raise ValueError('reporting unavailable')
                items.extend(page['items'])
                if not page['has_more']:return items
                if page['next_offset']<=offset:raise ValueError('reporting pagination did not advance')
                offset=page['next_offset']
            raise ValueError('reporting pagination exceeds bound')
        decisions=records('decision.observe')
        match=next((r for r in decisions if r['receipt']['request_sha256']==value['decision_receipt_sha256']),None)
        if match is None:raise ValueError('decision receipt unavailable')
        decision=match['submission'];body=decision['body'];context=decision['context']
        if (body['kind']!='architecture' or body['state']!='approved' or context['project_id']!=project_id or
                context['architecture']!=dict(document_id=documents[0]['document_id'],version=value['architecture_version'],markdown_sha256=value['architecture_sha256'])):
            raise ValueError('decision context differs')
        if next((r for r in decisions if r['submission']['body']['decision_id']==body['decision_id']),None)!=match:
            raise ValueError('decision has a newer observation')
        if self.verify_human(match) is not True:raise ValueError('independent human decision verification required')
        mappings=records('mapping.record')
        selected=next((r for r in mappings if r['submission']['body']['kind']=='execution' and r['submission']['body']['plan_id']==value['plan_id']),None)
        if selected is None:raise ValueError('execution mapping unavailable')
        mapping=selected['submission'];linear=mapping['body']['linear'];pin=mapping['context']['work']
        if (any(linear[k]!=value[v] for k,v in [('organization_id','organization_id'),('team_id','team_id'),('project_id','linear_project_id'),('issue_id','issue_id')]) or
                mapping['context']['architecture']!=context['architecture'] or
                pin!=dict(work_item_id=value['work_id'],work_revision_sha256=value['work_revision_sha256'],assignment_sha256=value['assignment_sha256'])):
            raise ValueError('execution mapping differs')
        expected={k:value[k] for k in ('organization_id','team_id','linear_project_id','issue_id')}
        if self.read_issue(value['issue_id'])!=expected:raise ValueError('native Linear issue differs')
        if self.verify_workspace(value) is not True:raise ValueError('workspace baseline or isolation unverified')
        return True
