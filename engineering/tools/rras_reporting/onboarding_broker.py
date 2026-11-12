"""Narrow planning dispatcher for an authenticated local transport.

The transport MUST supply a kernel-authenticated peer UID. `session_lookup`
is a trusted runtime journal lookup that returns a freshly verified native
origin for an active planning dispatch, not an agent assertion. `issue_read`
is a trusted native Linear read under the origin's separate app identity.
Neither callback is supplied by the request. This module is not a listener.
"""
import importlib.util
from pathlib import Path


def local(name):
    spec=importlib.util.spec_from_file_location('onboarding_broker_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


class Broker:
    def __init__(self,grants,session_lookup,issue_read,store):
        if type(grants) is not dict or not grants or not callable(session_lookup) or not callable(issue_read):
            raise ValueError('protected planning grants and readers required')
        self.grants,self.session_lookup,self.issue_read,self.store=grants,session_lookup,issue_read,store

    def dispatch(self,peer_uid,message):
        if type(peer_uid) is not int or peer_uid not in self.grants or type(message) is not dict:
            raise ValueError('planning peer refused')
        operation=message.get('operation')
        fields={'operation','dispatch_id','proposal'}
        if operation=='draft.work':fields.add('issue_id')
        elif operation!='draft.project':raise ValueError('unknown planning operation')
        if set(message)!=fields:raise ValueError('exact planning request required')
        d=local('onboarding_drafts');dispatch=d.identifier(message['dispatch_id'])
        # The selected dispatch is checked against the actual peer and an
        # active planning journal entry by this trusted callback on every call.
        origin=self.session_lookup(peer_uid,dispatch)
        origin=d.authorize(self.grants,lambda _:origin,peer_uid,None)
        if operation=='draft.project':
            return d.DraftWriter(self.grants,lambda _:origin,self.store).save(peer_uid,None,message['proposal'])
        issue_id=d.identifier(message['issue_id'])
        writer=local('onboarding_work').DraftWorkWriter(self.grants,lambda _:origin,
            lambda _:self.issue_read(dispatch,origin,issue_id),self.store)
        return writer.save(peer_uid,None,None,message['proposal'])
