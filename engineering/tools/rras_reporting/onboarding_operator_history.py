"""Operator-only history adapter for exact decision and designation writes.

Its history socket must belong to a distinct, protected operator service. Do
not expose this adapter or its underlying RPC to the planning agent.
"""
import importlib.util
from pathlib import Path


def local(name):
    spec=importlib.util.spec_from_file_location('operator_history_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


class Adapter:
    def __init__(self,rpc,allowed_scopes):
        if not callable(rpc):raise ValueError('protected operator history transport required')
        self.rpc=rpc
        # The planning adapter's bounded read only is reused; its draft writer
        # callbacks are intentionally unavailable through this interface.
        self.reader=local('onboarding_history').HistoryAdapter(rpc,lambda *_:None,lambda *_:None,allowed_scopes)

    def project(self,scope,project_id):return self.reader.project(scope,project_id)

    def observe_decision(self,value,decision_id):
        scope=self.reader.allowed(value['scope'])
        request=dict(contract='engineering-reporting.v1',operation='decision.observe',client_event_key='operator-decision:'+decision_id,
            expected_head=None,occurred_at=None,scope=scope,
            source=dict(kind='imported',namespace=value['source_namespace'],id=value['source_id']),
            context=dict(project_id=value['project_id'],architecture=dict(document_id=value['document_id'],
                version=value['version'],markdown_sha256=value['markdown_sha256']),work=None),
            body=dict(decision_id=decision_id,version=1,previous_sha256=None,kind='architecture',state='approved',
                attribution='imported_source',attributed_author=dict(role='human',runtime='linear',source_actor_id=value['human_actor_id']),
                source_reference=dict(namespace=value['source_namespace'],id=value['source_id'],sha256=value['source_sha256']),
                decision_text=value['decision_text']))
        return self.rpc(dict(method='reporting_submit',request=request))['receipt']['request_sha256']

    def designate(self,scope,project_id,head,version,digest,receipt):
        scope=self.reader.allowed(scope)
        request=dict(contract='engineering-project.v1',operation='architecture.designate',project_id=project_id,scope=scope,
            client_event_key='operator-designation:'+receipt,expected_head=head,occurred_at=None,
            source=dict(kind='imported',namespace='operator_decision',id=receipt),
            body=dict(version=version,markdown_sha256=digest,reason='Recorded exact operator decision receipt '+receipt))
        return self.rpc(dict(method='project_submit',request=request))
