"""Narrow history adapter for onboarding drafts; no server or privilege grant.

The process hosting this adapter must keep its underlying history credential
private from callers. `lookup_binding` must be an authoritative, access-safe
global lookup, not a search of only the caller's visible scopes. No production
lookup or transport is installed by this module.
"""
import importlib.util
from pathlib import Path
import re


def local(name):
    spec=importlib.util.spec_from_file_location('onboarding_history_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


class HistoryAdapter:
    def __init__(self, rpc, lookup_binding, reserve_binding, allowed_scopes):
        if not callable(rpc) or not callable(lookup_binding) or not callable(reserve_binding) or type(allowed_scopes) is not list or not allowed_scopes:
            raise ValueError('explicit protected history adapter required')
        draft=local('onboarding_drafts')
        self.scopes=[draft.selected_scope(scope) for scope in allowed_scopes]
        if len({(scope['kind'],scope['id']) for scope in self.scopes}) != len(self.scopes):
            raise ValueError('duplicate scopes refused')
        self.rpc,self.lookup_binding,self.reserve_binding=rpc,lookup_binding,reserve_binding

    def allowed(self, scope):
        scope=local('onboarding_drafts').selected_scope(scope)
        if scope not in self.scopes: raise ValueError('scope refused')
        return scope

    def binding(self, organization, linear_project):
        draft=local('onboarding_drafts');draft.identifier(organization);draft.identifier(linear_project)
        result=self.lookup_binding(organization,linear_project)
        if result is None:return None
        if type(result) is not dict or set(result)!={'project_id','scope','team_id'}:
            raise ValueError('authoritative binding response required')
        # Return no details if the global identity belongs to another scope.
        self.allowed(result['scope'])
        draft.identifier(result['team_id'])
        return dict(result)

    def reserve(self, origin, project_id):
        d=local('onboarding_drafts');origin=d.verified(origin);self.allowed(origin['scope'])
        if project_id!=d.identity('prj_',origin['organization_id'],origin['project_id']):
            raise ValueError('exact deterministic project identity required')
        return self.reserve_binding(origin['organization_id'],origin['project_id'],origin['team_id'],project_id,origin['scope'])

    def project(self, scope, project_id):
        scope=self.allowed(scope)
        if type(project_id) is not str or not re.fullmatch(r'prj_[0-9a-f]{32}',project_id):
            raise ValueError('project identity required')
        offset=0;snapshot=None
        # A bounded complete list is required to distinguish absence from denial
        # and to avoid silently duplicating a project after partial reads.
        for _ in range(256):
            query={'view':'projects','limit':50,'offset':offset,'archived':True}
            if snapshot is not None:query['snapshot']=snapshot
            result=self.rpc({'method':'project_read','scope':scope,'query':query})
            if snapshot is None:snapshot=result['snapshot']
            if any(row['project_id']==project_id for row in result['items']):
                result=self.rpc({'method':'project_read','scope':scope,
                                 'query':{'view':'project','project_id':project_id}})
                return result['project']
            if not result['has_more']:return None
            if result['next_offset']<=offset:raise ValueError('history pagination did not advance')
            offset=result['next_offset']
        raise ValueError('history project search exceeded bounded pages')

    def submit_project(self, request):
        if type(request) is not dict or request.get('operation') not in ('project.create','architecture.save'):
            raise ValueError('draft operations only')
        self.allowed(request.get('scope'))
        return self.rpc({'method':'planning_project_submit','request':request})

    def work(self, scope, work_id):
        scope=self.allowed(scope)
        if type(work_id) is not str or not re.fullmatch(r'wrk_[0-9a-f]{32}',work_id):raise ValueError('work identity required')
        offset=0;snapshot=None
        for _ in range(256):
            query={'view':'works','limit':50,'offset':offset}
            if snapshot is not None:query['snapshot']=snapshot
            result=self.rpc({'method':'project_read','scope':scope,'query':query})
            if snapshot is None:snapshot=result['snapshot']
            if any(row['work_item_id']==work_id for row in result['items']):
                return self.rpc({'method':'project_read','scope':scope,'query':{'view':'work','work_id':work_id}})
            if not result['has_more']:return None
            if result['next_offset']<=offset:raise ValueError('history pagination did not advance')
            offset=result['next_offset']
        raise ValueError('history work search exceeded bounded pages')

    def architecture(self, scope, project_id, version):
        scope=self.allowed(scope)
        if type(project_id) is not str or not re.fullmatch(r'prj_[0-9a-f]{32}',project_id) or type(version) is not int or version<1:
            raise ValueError('exact architecture required')
        return self.rpc({'method':'project_read','scope':scope,
                         'query':{'view':'architecture','project_id':project_id,'version':version}})['document']

    def reserve_work(self, origin, project_id, plan_id, issue_id, work_id):
        d=local('onboarding_drafts');origin=d.verified(origin);self.allowed(origin['scope']);d.identifier(issue_id)
        if (project_id!=d.identity('prj_',origin['organization_id'],origin['project_id']) or
                work_id!=d.work_identity('wrk_',origin['organization_id'],origin['project_id'],plan_id)):
            raise ValueError('exact deterministic work identity required')
        return self.rpc(dict(method='planning_work_reserve',organization_id=origin['organization_id'],
            linear_project_id=origin['project_id'],team_id=origin['team_id'],project_id=project_id,scope=origin['scope'],
            plan_id=plan_id,linear_issue_id=issue_id,work_id=work_id))

    def issue_binding(self, origin, issue_id):
        d=local('onboarding_drafts');origin=d.verified(origin);d.identifier(issue_id);self.allowed(origin['scope'])
        return self.rpc(dict(method='planning_issue_binding',organization_id=origin['organization_id'],linear_issue_id=issue_id))

    def submit_work(self, project_id, plan_id, request):
        if type(request) is not dict or request.get('operation')!='work.create':raise ValueError('draft work creation only')
        return self.rpc(dict(method='planning_work_submit',project_id=project_id,plan_id=plan_id,request=request))

    def submit_membership(self, plan_id, request):
        if type(request) is not dict or request.get('operation') not in ('membership.assign','membership.designate'):
            raise ValueError('draft membership only')
        return self.rpc(dict(method='planning_membership_submit',project_id=request['project_id'],plan_id=plan_id,request=request))

    def submit_work_mapping(self, origin, issue, project_id, document_id, digest, plan_id, work_id, revision, assignment):
        d=local('onboarding_drafts');origin=d.verified(origin);scope=self.allowed(origin['scope'])
        mapping_id=d.work_identity('map_',origin['organization_id'],origin['project_id'],plan_id)
        request=dict(contract='engineering-reporting.v1',operation='mapping.record',client_event_key='onboard-work-map:'+work_id,
            expected_head=None,occurred_at=None,scope=scope,
            source=dict(kind='agent_reported',namespace='linear_'+origin['agent'],id=origin['source_session']),
            context=dict(project_id=project_id,architecture=dict(document_id=document_id,version=1,markdown_sha256=digest),
                work=dict(work_item_id=work_id,work_revision_sha256=revision,assignment_sha256=assignment)),
            body=dict(mapping_id=mapping_id,version=1,previous_sha256=None,kind='execution',plan_id=plan_id,
                linear=dict(organization_id=origin['organization_id'],team_id=origin['team_id'],project_id=origin['project_id'],
                            issue_id=issue['id'],identifier=issue['identifier'],url=issue['url']),
                reason='Link a proposed draft work item to its verified Linear issue.'))
        return self.rpc({'method':'planning_reporting_submit','request':request})

    def submit_mapping(self, origin, project_id, document_id, digest):
        d=local('onboarding_drafts');origin=d.verified(origin);scope=self.allowed(origin['scope'])
        if project_id != d.identity('prj_',origin['organization_id'],origin['project_id']) or document_id != d.identity('doc_',origin['organization_id'],origin['project_id']):
            raise ValueError('exact deterministic project identity required')
        if type(digest) is not str or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('architecture digest required')
        mapping_id=d.identity('map_',origin['organization_id'],origin['project_id'])
        request=dict(contract='engineering-reporting.v1',operation='mapping.record',client_event_key='onboard-map:'+project_id,
            expected_head=None,occurred_at=None,scope=scope,
            source=dict(kind='agent_reported',namespace='linear_'+origin['agent'],id=origin['source_session']),
            context=dict(project_id=project_id,architecture=dict(document_id=document_id,version=1,markdown_sha256=digest),work=None),
            body=dict(mapping_id=mapping_id,version=1,previous_sha256=None,kind='project',plan_id=None,
                linear=dict(organization_id=origin['organization_id'],team_id=origin['team_id'],project_id=origin['project_id'],
                            issue_id=None,identifier=origin['project_identifier'],url=origin['project_url']),
                reason='Link the retained unapproved draft to its exact Linear project.'))
        return self.rpc({'method':'planning_reporting_submit','request':request})
