"""Bind planning admission and broker lookups to retained dispatches."""
import hashlib
import importlib.util
import json
from pathlib import Path


def local(name):
    spec=importlib.util.spec_from_file_location('planning_context_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


class Context:
    def __init__(self,connection,reader,organization_id,app_user_id,peer_uid):
        d=local('onboarding_drafts');d.identifier(organization_id);d.identifier(app_user_id)
        if type(peer_uid) is not int or peer_uid<0 or not callable(getattr(reader,'origin',None)):
            raise ValueError('protected planning context required')
        self.connection,self.reader=connection,reader
        self.organization_id,self.app_user_id,self.peer_uid=organization_id,app_user_id,peer_uid

    def verify_event(self,event):
        fields={'dispatch_id','session_id','issue_id','organization_id','app_user_id','message'}
        if type(event) is not dict or set(event)!=fields:return False
        if event['organization_id']!=self.organization_id or event['app_user_id']!=self.app_user_id:return False
        origin=self.reader.origin(event['dispatch_id'],event['issue_id'],message=event['message'],session=event['session_id'])
        return (origin['organization_id']==self.organization_id and origin['source_session']==event['session_id'] and origin['agent']=='codex')

    def active(self,peer,dispatch):
        local('onboarding_drafts').identifier(dispatch)
        if peer!=self.peer_uid:return False
        with self.connection() as db:
            row=db.execute('SELECT state FROM planning_turns WHERE dispatch=?',(dispatch,)).fetchone()
        return row is not None and row[0] in ('preparing','running','interrupt_requested')

    def native(self,dispatch):
        local('onboarding_drafts').identifier(dispatch)
        if not self.active(self.peer_uid,dispatch):raise ValueError('active retained planning dispatch required')
        with self.connection() as db:
            row=db.execute('SELECT request,sha256 FROM planning_turns WHERE dispatch=?',(dispatch,)).fetchone()
        if row is None or hashlib.sha256(row[0]).hexdigest()!=row[1]:raise ValueError('planning dispatch digest differs')
        request=json.loads(row[0]);origin=self.reader.origin(dispatch,request['issue_id'],message=request['message'],session=request['session_id'])
        if (request['dispatch_id']!=dispatch or request['organization_id']!=self.organization_id or
                request['app_user_id']!=self.app_user_id or origin['source_session']!=request['session_id'] or
                origin['organization_id']!=self.organization_id or origin['agent']!='codex'):
            raise ValueError('native planning context changed')
        return origin

    def verify_stop(self,value):
        fields={'stop_dispatch_id','target_dispatch_id','session_id','issue_id','organization_id','app_user_id','message'}
        if type(value) is not dict or set(value)!=fields:return False
        if value['organization_id']!=self.organization_id or value['app_user_id']!=self.app_user_id:return False
        d=local('onboarding_drafts')
        for key in fields-{'message'}:d.identifier(value[key])
        origin=self.reader.origin(value['stop_dispatch_id'],value['issue_id'],message=value['message'],session=value['session_id'],stop=True)
        with self.connection() as db:
            row=db.execute('SELECT session,issue,state FROM planning_turns WHERE dispatch=?',(value['target_dispatch_id'],)).fetchone()
        return (origin['organization_id']==self.organization_id and origin['agent']=='codex' and
                row is not None and row[0]==value['session_id'] and row[1]==value['issue_id'] and row[2] in ('running','interrupt_requested'))
