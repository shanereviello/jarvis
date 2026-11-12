"""Create and map a proposed work item without granting execution authority.

Both verifier callbacks and the protected history adapter must be supplied by
trusted infrastructure; this module does not authenticate JSON assertions.
"""
import importlib.util
import hashlib
from pathlib import Path
import re
from urllib.parse import urlsplit


def local(name):
    spec=importlib.util.spec_from_file_location('onboarding_work_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


class DraftWorkWriter:
    def __init__(self,grants,verify_origin,verify_issue,store):
        if type(grants) is not dict or not grants or not callable(verify_origin) or not callable(verify_issue):
            raise ValueError('protected planning and issue verification required')
        self.grants,self.verify_origin,self.verify_issue,self.store=grants,verify_origin,verify_issue,store

    def save(self,peer_uid,evidence,issue_evidence,value):
        d=local('onboarding_drafts');origin=d.authorize(self.grants,self.verify_origin,peer_uid,evidence)
        fields={'plan_id','title','objective','rationale','allowed_paths','acceptance_criteria'}
        if type(value) is not dict or set(value)!=fields:raise ValueError('exact proposed work required')
        plan=value['plan_id']
        if type(plan) is not str or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,95}',plan):raise ValueError('plan identity required')
        for key in ('title','objective','rationale'):d.text(value[key],200 if key=='title' else 16384,single_line=(key=='title'))
        if len(plan+': '+value['title'])>200:raise ValueError('bounded full work title required')
        if type(value['allowed_paths']) is not list or type(value['acceptance_criteria']) is not list:
            raise ValueError('bounded work details required')
        issue=self.verify_issue(issue_evidence)
        if type(issue) is not dict or set(issue)!={'organization_id','team_id','project_id','id','identifier','url'}:
            raise ValueError('verified Linear issue required')
        for key in ('organization_id','team_id','project_id','id'):d.identifier(issue[key])
        if any(issue[key]!=origin[key] for key in ('organization_id','team_id','project_id')):
            raise ValueError('issue project identity differs')
        d.text(issue['identifier'],128,single_line=True)
        url=urlsplit(d.text(issue['url'],2048))
        if url.scheme!='https' or url.netloc!='linear.app' or url.query or url.fragment:
            raise ValueError('credential-free Linear issue URL required')
        org,linear=origin['organization_id'],origin['project_id']
        pid=d.identity('prj_',org,linear);doc_id=d.identity('doc_',org,linear);wid=d.work_identity('wrk_',org,linear,plan)
        project=self.store.project(origin['scope'],pid)
        if project is None or project['governing_version'] is not None or len(project['architecture'])!=1:
            raise ValueError('unapproved retained draft required')
        doc=project['architecture'][0]
        if doc['document_id']!=doc_id or doc['version']!=1:raise ValueError('exact initial draft required')
        markdown=self.store.architecture(origin['scope'],pid,1)['markdown']
        if hashlib.sha256(markdown.encode('utf-8')).hexdigest()!=doc['markdown_sha256']:
            raise ValueError('retained draft digest differs')
        if not re.search(r'(?<![A-Za-z0-9_.-])'+re.escape(plan)+r'(?![A-Za-z0-9_.-])',markdown):
            raise ValueError('plan ID must appear in retained draft')
        parent=self.store.binding(org,linear)
        if parent is None or parent['project_id']!=pid or parent['scope']!=origin['scope']:
            raise ValueError('exact retained project mapping required')
        body=dict(work_item_id=wid,revision=1,title=plan+': '+value['title'],objective=value['objective'],rationale=value['rationale'],
                  baseline=None,allowed_paths=value['allowed_paths'],acceptance_criteria=value['acceptance_criteria'])
        if origin['scope']['kind']=='repository':body['repository_id']=origin['scope']['id'];contract='engineering-history.v1'
        else:body['scope']=origin['scope'];contract='engineering-history.v2'
        source=dict(kind='agent_reported',namespace='linear_'+origin['agent'],id=origin['source_session'])
        request=dict(contract=contract,operation='work.create',client_event_key='onboard-work:'+wid,
                     expected_head=None,occurred_at=None,source=source,body=body)
        # Reservations are permanent. Reject malformed or oversized proposals
        # before consuming an issue or plan identity.
        path=Path(__file__).resolve().parent.parent/'rras_history'/'contract.py'
        spec=importlib.util.spec_from_file_location('onboarding_work_contract',path)
        history_contract=importlib.util.module_from_spec(spec);spec.loader.exec_module(history_contract)
        history_contract.validate(request)
        self.store.reserve_work(origin,pid,plan,issue['id'],wid)
        binding=self.store.issue_binding(origin,issue['id'])
        expected=dict(project_id=pid,scope=origin['scope'],team_id=origin['team_id'],linear_project_id=linear,plan_id=plan,work_id=wid)
        if binding is not None and binding!=expected:raise ValueError('conflicting existing issue binding')
        existing=self.store.work(origin['scope'],wid)
        if existing is None:
            self.store.submit_work(pid,plan,request)
            existing=self.store.work(origin['scope'],wid)
        if existing is None or existing['work']!=body:raise ValueError('existing work differs; reconcile explicitly')
        assignment=existing['assignment']
        common=dict(contract='engineering-project.v1',project_id=pid,scope=origin['scope'],occurred_at=None,source=source)
        if assignment is None:
            self.store.submit_membership(plan,dict(common,operation='membership.assign',client_event_key='onboard-assign:'+wid,
                expected_head=self.store.project(origin['scope'],pid)['head'],body=dict(work_item_id=wid,architecture_version=None,
                expected_assignment_sha256=None,expected_previous_project_head=None,reason='Assign proposed work before architecture agreement.')))
            assignment=self.store.work(origin['scope'],wid)['assignment']
        if assignment['project_id']!=pid:raise ValueError('work has another project; reconcile explicitly')
        if assignment['architecture_version'] is None:
            self.store.submit_membership(plan,dict(common,operation='membership.designate',client_event_key='onboard-draft-pin:'+wid,
                expected_head=self.store.project(origin['scope'],pid)['head'],body=dict(work_item_id=wid,architecture_version=1,
                expected_assignment_sha256=assignment['assignment_sha256'],reason='Associate work with the unapproved draft; no execution authority.')))
            assignment=self.store.work(origin['scope'],wid)['assignment']
        if assignment['project_id']!=pid or assignment['architecture_version']!=1:raise ValueError('draft assignment differs')
        if binding is None:
            self.store.submit_work_mapping(origin,issue,pid,doc_id,doc['markdown_sha256'],plan,wid,
                                           existing['work_revision_sha256'],assignment['assignment_sha256'])
        if self.store.issue_binding(origin,issue['id'])!=expected:raise ValueError('issue mapping outcome uncertain; reconcile')
        return dict(project_id=pid,plan_id=plan,work_id=wid,issue_id=issue['id'],designation='draft',execution_authorized=False)
