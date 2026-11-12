"""Loopback-only non-retrying transport for a proposed Linear issue."""
import http.client
import importlib.util
import json
from pathlib import Path
from urllib.parse import urlsplit


def local(name):
    spec=importlib.util.spec_from_file_location('planning_create_http_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


class Creator:
    def __init__(self,url,app_id,token):
        local('onboarding_drafts').identifier(app_id)
        p=urlsplit(url)
        if (p.scheme!='http' or p.hostname!='127.0.0.1' or p.username or p.password or p.query or p.fragment or
                p.port is None or p.path!='/webhook/rras-planning-create-'+app_id or type(token) is not bytes or
                not 32<=len(token)<=256 or not all(33<=x<=126 for x in token)):
            raise ValueError('fixed private issue creator required')
        self.port,self.path,self.token=p.port,p.path,token

    def create(self,dispatch,plan,proposal):
        local('onboarding_drafts').identifier(dispatch)
        raw=json.dumps(dict(dispatch_id=dispatch,plan_id=plan,proposal=proposal),separators=(',',':'),allow_nan=False).encode()
        if len(raw)>65536:raise ValueError('bounded issue creation required')
        connection=http.client.HTTPConnection('127.0.0.1',self.port,timeout=20)
        try:
            connection.request('POST',self.path,body=raw,headers={'Content-Type':'application/json','Authorization':'Bearer '+self.token.decode('ascii')})
            response=connection.getresponse();body=response.read(65537)
            if response.status!=200 or len(body)>65536:raise ValueError('issue creation outcome unconfirmed')
            def pairs(items):
                result={}
                for key,value in items:
                    if key in result:raise ValueError('duplicate response field')
                    result[key]=value
                return result
            value=json.loads(body,object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('invalid response')))
            if (type(value) is not dict or set(value)!={'contract','dispatch_id','created','issue_id'} or
                    value['contract']!='codex-planning-create.v1' or value['dispatch_id']!=dispatch or value['created'] is not True):
                raise ValueError('issue creation outcome unconfirmed')
            return local('onboarding_drafts').identifier(value['issue_id'])
        finally:connection.close()
