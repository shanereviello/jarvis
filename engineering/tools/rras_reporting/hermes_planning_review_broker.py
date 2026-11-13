"""Prepare an operator-owned review for an independently verified Jarvis run."""
import importlib.util
from pathlib import Path


def local(name):
    spec=importlib.util.spec_from_file_location('hermes_review_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


class Broker:
    def __init__(self,peer_uid,resolve_native,read_issue,connection,history,scopes,team_id):
        if type(peer_uid) is not int or peer_uid<=0 or not all(callable(x) for x in (resolve_native,read_issue,connection)):
            raise ValueError('protected Jarvis review boundaries required')
        local('onboarding_drafts').identifier(team_id)
        self.peer_uid,self.resolve_native,self.read_issue,self.connection,self.history,self.scopes,self.team_id=(peer_uid,resolve_native,read_issue,connection,history,scopes,team_id)

    def dispatch(self,peer,message):
        if (type(peer) is not int or peer!=self.peer_uid or type(message) is not dict or
            set(message)!={'operation','native','issue_id','version'} or message['operation']!='review.prepare'):
            raise ValueError('exact trusted Jarvis review request required')
        native=message['native'];origin=self.resolve_native(peer,native)
        d=local('onboarding_drafts');origin=d.verified(origin);issue_id=d.identifier(message['issue_id'])
        if origin['agent']!='jarvis' or origin['source_session']!=native['session_id'] or origin['team_id']!=self.team_id:
            raise ValueError('verified Jarvis origin required')
        issue=self.read_issue(native,origin,issue_id)
        if type(issue) is not dict or issue.get('id')!=issue_id:raise ValueError('verified issue required')
        selected={key:issue[key] for key in ('organization_id','team_id','project_id','id')}
        store=local('onboarding_review_store').ReviewStore(self.connection,self.history,lambda _:selected,self.scopes)
        review_id=store.prepare(origin,issue_id,message['version']);review=store.read(review_id)
        return dict(review_id=review_id,project_id=review['project_id'],issue_id=review['issue_id'],version=review['version'],
            markdown_sha256=review['markdown_sha256'],human_approval_inferred=False,execution_authorized=False)
