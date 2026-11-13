"""Private, non-retrying Jarvis issue-create transport."""
import http.client
import importlib.util
import json
from pathlib import Path
from urllib.parse import urlsplit


def local(name):
    spec=importlib.util.spec_from_file_location('hermes_create_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


class Creator:
    def __init__(self,url,app_id,token):
        local('onboarding_drafts').identifier(app_id);p=urlsplit(url)
        if (p.scheme!='http' or p.hostname!='127.0.0.1' or p.username or p.password or p.query or p.fragment or
            p.port is None or p.path!='/webhook/rras-jarvis-planning-create-'+app_id or type(token) is not bytes or
            not 32<=len(token)<=256 or not all(33<=x<=126 for x in token)):
            raise ValueError('fixed private Jarvis creator required')
        self.port,self.path,self.token=p.port,p.path,token

    def create(self,native,plan,proposal):
        if local('hermes_native_context').parse('api_server',native.get('hermes_session_id'),native.get('run_id'))!=native:
            raise ValueError('exact native context required')
        raw=json.dumps(dict(native=native,plan_id=plan,proposal=proposal),separators=(',',':'),allow_nan=False).encode()
        if len(raw)>65536:raise ValueError('bounded draft required')
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
            if (type(value) is not dict or set(value)!={'contract','native','created','issue_id'} or
                value['contract']!='hermes-planning-create.v1' or value['native']!=native or value['created'] is not True):
                raise ValueError('issue creation outcome unconfirmed')
            return local('onboarding_drafts').identifier(value['issue_id'])
        finally:connection.close()
