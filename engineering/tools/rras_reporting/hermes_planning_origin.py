"""Validate a trusted live native Jarvis planning origin and fixed scope."""
import importlib.util
from pathlib import Path


def local(name):
    spec=importlib.util.spec_from_file_location('hermes_planning_origin_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


class Resolver:
    def __init__(self, peer_uid, organization_id, app_user_id, read_native, resolve_scope):
        drafts=local('onboarding_drafts');drafts.identifier(organization_id);drafts.identifier(app_user_id)
        if type(peer_uid) is not int or peer_uid<=0 or not callable(read_native) or not callable(resolve_scope):
            raise ValueError('protected Jarvis native readers required')
        self.peer_uid,self.organization_id,self.app_user_id=peer_uid,organization_id,app_user_id
        self.read_native,self.resolve_scope=read_native,resolve_scope

    def __call__(self, peer, native):
        if type(peer) is not int or peer!=self.peer_uid or type(native) is not dict:
            raise ValueError('protected Jarvis planning peer required')
        parsed=local('hermes_native_context').parse('api_server',native.get('hermes_session_id'),native.get('run_id'))
        if parsed!=native or parsed['organization_id']!=self.organization_id:
            raise ValueError('exact native Jarvis context required')
        result=self.read_native(dict(native))
        fields={'contract','native','app_user_id','active','source_verified','origin'}
        if (type(result) is not dict or set(result)!=fields or result['contract']!='hermes-planning-origin.v1' or
                result['native']!=native or result['app_user_id']!=self.app_user_id or
                result['active'] is not True or result['source_verified'] is not True):
            raise ValueError('active verified Jarvis origin required')
        drafts=local('onboarding_drafts');origin=drafts.verified(result['origin'])
        if (origin['agent']!='jarvis' or origin['organization_id']!=self.organization_id or
                origin['source_session']!=native['session_id'] or
                drafts.selected_scope(self.resolve_scope(origin['project_id']))!=origin['scope']):
            raise ValueError('Jarvis project scope or origin differs')
        return origin
