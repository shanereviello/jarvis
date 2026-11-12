"""Create one proposed Linear issue, then link its draft work in history.

Creation is supplied by a trusted private transport. This coordinator stores a
durable intent before calling it and never repeats an uncertain create.
"""
import hashlib
import importlib.util
from pathlib import Path
import re


def local(name):
    spec=importlib.util.spec_from_file_location('planning_issue_create_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


class Creator:
    def __init__(self,grants,verify_origin,verify_issue,store,journal,create_issue):
        if not all(callable(value) for value in (verify_origin,verify_issue,create_issue)):
            raise ValueError('trusted planning creation boundaries required')
        self.grants,self.verify_origin,self.verify_issue,self.store,self.journal,self.create_issue=(
            grants,verify_origin,verify_issue,store,journal,create_issue)

    def create(self,peer,evidence,value):
        d=local('onboarding_drafts');origin=d.authorize(self.grants,self.verify_origin,peer,evidence)
        fields={'plan_id','title','objective','rationale','allowed_paths','acceptance_criteria'}
        if type(value) is not dict or set(value)!=fields:raise ValueError('exact draft work required')
        plan=value['plan_id']
        if type(plan) is not str or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,95}',plan):raise ValueError('exact plan required')
        org,linear=origin['organization_id'],origin['project_id']
        pid=d.identity('prj_',org,linear);doc=d.identity('doc_',org,linear);wid=d.work_identity('wrk_',org,linear,plan)
        project=self.store.project(origin['scope'],pid)
        if project is None or project['governing_version'] is not None or len(project['architecture'])!=1:
            raise ValueError('unapproved retained draft required')
        architecture=project['architecture'][0]
        if architecture['document_id']!=doc or architecture['version']!=1:raise ValueError('exact initial draft required')
        markdown=self.store.architecture(origin['scope'],pid,1)['markdown']
        if (hashlib.sha256(markdown.encode()).hexdigest()!=architecture['markdown_sha256'] or
                not re.search(r'(?<![A-Za-z0-9_.-])'+re.escape(plan)+r'(?![A-Za-z0-9_.-])',markdown)):
            raise ValueError('plan absent from exact retained draft')
        binding=self.store.binding(org,linear)
        if binding is None or binding['project_id']!=pid or binding['scope']!=origin['scope'] or binding['team_id']!=origin['team_id']:
            raise ValueError('exact retained project mapping required')
        body=dict(work_item_id=wid,revision=1,title=plan+': '+d.text(value['title'],200,single_line=True),
            objective=value['objective'],rationale=value['rationale'],baseline=None,
            allowed_paths=value['allowed_paths'],acceptance_criteria=value['acceptance_criteria'])
        if origin['scope']['kind']=='repository':body['repository_id']=origin['scope']['id'];contract='engineering-history.v1'
        else:body['scope']=origin['scope'];contract='engineering-history.v2'
        request=dict(contract=contract,operation='work.create',client_event_key='onboard-work:'+wid,expected_head=None,occurred_at=None,
            source=dict(kind='agent_reported',namespace='linear_'+origin['agent'],id=origin['source_session']),body=body)
        path=Path(__file__).resolve().parent.parent/'rras_history'/'contract.py'
        spec=importlib.util.spec_from_file_location('planning_issue_create_contract',path)
        contract_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(contract_module);contract_module.validate(request)
        proposal=dict(title=body['title'],description='Proposed work from architecture plan '+plan+'.\n\n'+value['objective']+
                      '\n\n<!-- rras-draft-work:'+wid+' -->')
        identity=dict(organization_id=org,team_id=origin['team_id'],project_id=linear)
        result=self.journal.create_once(identity,plan,proposal,
            lambda body:self.create_issue(origin,plan,body),lambda issue_id:self.verify_issue(origin,issue_id))
        if result['state']!='complete':return dict(state='uncertain',execution_authorized=False)
        issue_id=result['issue_id']
        writer=local('onboarding_work').DraftWorkWriter(self.grants,lambda _:origin,lambda _:self.verify_issue(origin,issue_id),self.store)
        mapped=writer.save(peer,None,None,value)
        return dict(state='complete',issue_id=issue_id,work_id=mapped['work_id'],project_id=pid,plan_id=plan,execution_authorized=False)
