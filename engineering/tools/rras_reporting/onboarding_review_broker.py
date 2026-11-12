"""Narrow review preparation; never confirms authorship or designates.

Kernel peer identity, active native dispatch verification, and Linear issue
reads must be supplied by the protected host. This broker can prepare a review
reference only; a planner cannot call the operator attestation or recorder.
"""
import importlib.util
from pathlib import Path


def local(name):
    spec=importlib.util.spec_from_file_location('review_broker_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


class Broker:
    def __init__(self,grants,verify_origin,read_issue,connection,history,scopes):
        if type(grants) is not dict or not grants or not callable(verify_origin) or not callable(read_issue) or not callable(connection):
            raise ValueError('protected planning grants and native readers required')
        self.grants,self.verify_origin,self.read_issue,self.connection,self.history,self.scopes=grants,verify_origin,read_issue,connection,history,scopes

    def dispatch(self,peer_uid,message):
        if type(peer_uid) is not int or peer_uid not in self.grants or type(message) is not dict:
            raise ValueError('planning peer refused')
        if set(message)!={'operation','dispatch_id','issue_id','version'} or message['operation']!='review.prepare':
            raise ValueError('review preparation only')
        d=local('onboarding_drafts');dispatch=d.identifier(message['dispatch_id']);issue_id=d.identifier(message['issue_id'])
        origin=d.authorize(self.grants,lambda _:self.verify_origin(peer_uid,dispatch,issue_id),peer_uid,None)
        issue=self.read_issue(dispatch,origin,issue_id)
        if type(issue) is not dict or issue.get('id')!=issue_id:raise ValueError('verified review issue required')
        selected={k:issue[k] for k in ('organization_id','team_id','project_id','id')}
        store=local('onboarding_review_store').ReviewStore(self.connection,self.history,lambda _:selected,self.scopes)
        review_id=store.prepare(origin,issue_id,message['version'])
        review=store.read(review_id)
        return dict(review_id=review_id,project_id=review['project_id'],issue_id=review['issue_id'],version=review['version'],
                    markdown_sha256=review['markdown_sha256'],human_approval_inferred=False,execution_authorized=False)
