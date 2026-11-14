"""Jarvis planning broker with a reverified native run on every operation.

The caller identity comes from a trusted transport, and the resolver must read
the live native run and Linear origin independently. No agent-supplied project,
scope, actor or dispatch ID is accepted as proof of authority.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import uuid


def local(name):
    spec=importlib.util.spec_from_file_location('hermes_planning_broker_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def dispatch_id(native):
    raw=json.dumps(native,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
    return str(uuid.uuid5(uuid.NAMESPACE_URL,'rras-hermes-planning-v1:'+hashlib.sha256(raw).hexdigest()))


class Broker:
    def __init__(self, grants, resolve_native, issue_read, store, *, issue_journal=None, issue_create=None, review_prepare=None):
        if type(grants) is not dict or not grants or not callable(resolve_native) or not callable(issue_read):
            raise ValueError('protected Jarvis planning grants and readers required')
        if (issue_journal is None)!=(issue_create is None) or (issue_create is not None and not callable(issue_create)):
            raise ValueError('paired protected issue creation required')
        if review_prepare is not None and not callable(review_prepare):raise ValueError('protected review preparation required')
        self.grants,self.resolve_native,self.issue_read,self.store=grants,resolve_native,issue_read,store
        self.issue_journal,self.issue_create,self.review_prepare=issue_journal,issue_create,review_prepare

    def origin(self, peer, native):
        context=local('hermes_native_context');drafts=local('onboarding_drafts')
        if (type(peer) is not int or peer not in self.grants or type(native) is not dict or
                set(native)!={'organization_id','session_id','hermes_session_id','run_id'} or
                context.parse('api_server',native['hermes_session_id'],native['run_id'])!=native):
            raise ValueError('exact bound Jarvis run required')
        origin=drafts.authorize(self.grants,lambda _:self.resolve_native(peer,dict(native)),peer,None)
        if (origin['agent']!='jarvis' or origin['organization_id']!=native['organization_id'] or
                origin['source_session']!=native['session_id']):
            raise ValueError('native Jarvis planning origin differs')
        return origin

    def resolve(self,peer,frame):
        if type(frame) is not dict or set(frame)!={'contract','native'} or frame['contract']!='hermes-planning-native.v1':
            raise ValueError('exact native planning frame required')
        origin=self.origin(peer,frame['native'])
        return dict(dispatch_id=dispatch_id(frame['native']),origin=origin,execution_authorized=False)

    def submit(self,peer,frame):
        if type(frame) is not dict or set(frame)!={'contract','native','message'} or frame['contract']!='hermes-planning-submit.v1':
            raise ValueError('exact native planning submission required')
        native=frame['native'];origin=self.origin(peer,native);message=frame['message'];drafts=local('onboarding_drafts')
        if type(message) is not dict or message.get('dispatch_id')!=dispatch_id(native):
            raise ValueError('planning dispatch differs from native run')
        operation=message.get('operation')
        if operation=='review.prepare':
            if self.review_prepare is None or set(message)!={'operation','dispatch_id','issue_id','version'}:
                raise ValueError('protected review unavailable')
            return self.review_prepare(native,origin,drafts.identifier(message['issue_id']),message['version'])
        fields={'operation','dispatch_id','proposal'}
        if operation=='draft.work':fields.add('issue_id')
        elif operation not in ('draft.project','draft.issue'):raise ValueError('unknown planning operation')
        if set(message)!=fields:raise ValueError('exact planning request required')
        if operation=='draft.project':
            return drafts.DraftWriter(self.grants,lambda _:origin,self.store).save(peer,None,message['proposal'])
        if operation=='draft.issue':
            if self.issue_journal is None:raise ValueError('draft issue creation unavailable')
            creator=local('onboarding_issue_create').Creator(self.grants,lambda _:origin,
                lambda selected,issue:self.issue_read(native,selected,issue),self.store,self.issue_journal,
                lambda selected,plan,proposal:self.issue_create(native,selected,plan,proposal))
            return creator.create(peer,None,message['proposal'])
        issue=drafts.identifier(message['issue_id'])
        writer=local('onboarding_work').DraftWorkWriter(self.grants,lambda _:origin,
            lambda _:self.issue_read(native,origin,issue),self.store)
        return writer.save(peer,None,None,message['proposal'])
