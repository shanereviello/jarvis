"""Record an exact verified operator decision; no transport or operator credential.

The caller must be a protected operator-side broker. `verify_decision` must
independently validate the native source and human attribution; agent-provided
JSON is not evidence. This module cannot authenticate a human by itself.
"""
import importlib.util
import hashlib
import re
import uuid
from pathlib import Path


def local(name):
    spec=importlib.util.spec_from_file_location('onboarding_decision_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


class DecisionRecorder:
    def __init__(self, verify_decision, store, allowed_scopes):
        if not callable(verify_decision) or type(allowed_scopes) is not list or not allowed_scopes:
            raise ValueError('protected operator decision boundary required')
        self.verify_decision,self.store=verify_decision,store
        self.scopes=[local('onboarding_drafts').selected_scope(value) for value in allowed_scopes]

    def approve(self, evidence):
        value=self.verify_decision(evidence)
        fields={'organization_id','linear_project_id','scope','project_id','document_id','version',
                'markdown_sha256','expected_governing_version','expected_project_head',
                'human_actor_id','source_id','source_namespace','source_sha256','decision_text'}
        if type(value) is not dict or set(value)!=fields:raise ValueError('verified human decision required')
        d=local('onboarding_drafts');d.identifier(value['organization_id']);d.identifier(value['linear_project_id'])
        d.identifier(value['human_actor_id']);scope=d.selected_scope(value['scope'])
        if scope not in self.scopes:raise ValueError('decision scope refused')
        if (value['project_id']!=d.identity('prj_',value['organization_id'],value['linear_project_id']) or
                value['document_id']!=d.identity('doc_',value['organization_id'],value['linear_project_id'])):
            raise ValueError('decision project identity differs')
        if type(value['version']) is not int or value['version']<1:raise ValueError('exact architecture version required')
        if type(value['markdown_sha256']) is not str or not re.fullmatch('[0-9a-f]{64}',value['markdown_sha256']):
            raise ValueError('exact architecture digest required')
        prior=value['expected_governing_version']
        if prior is not None and (type(prior) is not int or prior<1):raise ValueError('exact prior designation required')
        if type(value['expected_project_head']) is not str or not re.fullmatch('[0-9a-f]{64}',value['expected_project_head']):
            raise ValueError('exact reviewed project head required')
        for key in ('source_id','source_namespace','decision_text'):d.text(value[key],512 if key!='decision_text' else 16384)
        if (type(value['source_sha256']) is not str or
                hashlib.sha256(value['decision_text'].encode('utf-8')).hexdigest()!=value['source_sha256']):
            raise ValueError('exact verified decision source bytes required')
        if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,95}',value['source_namespace']):
            raise ValueError('exact decision source namespace required')
        project=self.store.project(scope,value['project_id'])
        if project is None or project['scope']!=scope:raise ValueError('project unavailable')
        matches=[doc for doc in project['architecture'] if doc['document_id']==value['document_id'] and
                 doc['version']==value['version'] and doc['markdown_sha256']==value['markdown_sha256']]
        if len(matches)!=1:raise ValueError('exact retained architecture required')
        if project['governing_version']!=value['version'] and (
                project['governing_version']!=prior or project['head']!=value['expected_project_head']):
            raise ValueError('current governing version changed; review required')
        decision_id='dec_'+uuid.uuid5(uuid.NAMESPACE_URL,'rras-onboarding-decision-v1:'+value['source_namespace']+':'+value['source_id']).hex
        # The protected adapter retains an observation before designation. An
        # observation or its receipt alone never grants execution authority.
        receipt=self.store.observe_decision(value,decision_id)
        if not receipt or not re.fullmatch('[0-9a-f]{64}',receipt):raise ValueError('decision receipt unconfirmed')
        if project['governing_version']!=value['version']:
            self.store.designate(scope,value['project_id'],project['head'],value['version'],value['markdown_sha256'],receipt)
        confirmed=self.store.project(scope,value['project_id'])
        if confirmed is None or confirmed['governing_version']!=value['version']:
            raise ValueError('designation outcome uncertain; reconcile before retry')
        return {'project_id':value['project_id'],'version':value['version'],'markdown_sha256':value['markdown_sha256'],
                'decision_receipt_sha256':receipt,'execution_authorized':False}
