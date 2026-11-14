"""Loopback-only authenticated calls to configured n8n planning readers."""
import http.client
import importlib.util
import json
from pathlib import Path
from urllib.parse import urlsplit


def local(name):
    spec=importlib.util.spec_from_file_location('planning_reader_http_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


class Reader:
    def __init__(self,origin_url,issue_url,app_id,token):
        d=local('onboarding_drafts');d.identifier(app_id)
        if type(token) is not bytes or not 32<=len(token)<=256 or not all(33<=x<=126 for x in token):
            raise ValueError('private reader credential required')
        self.paths={}
        for name,url in [('origin',origin_url),('issue',issue_url)]:
            if type(url) is not str:raise ValueError('exact private reader endpoint required')
            parsed=urlsplit(url)
            if (parsed.scheme!='http' or parsed.hostname!='127.0.0.1' or parsed.username or parsed.password or
                parsed.query or parsed.fragment or parsed.port is None or not 1<=parsed.port<=65535 or
                parsed.path!='/webhook/rras-planning-'+name+'-'+app_id):
                raise ValueError('fixed loopback planning reader required')
            self.paths[name]=(parsed.port,parsed.path)
        self.token=token

    def request(self,name,value):
        port,path=self.paths[name];raw=json.dumps(value,separators=(',',':'),allow_nan=False).encode()
        if len(raw)>4096:raise ValueError('bounded planning reader request required')
        connection=http.client.HTTPConnection('127.0.0.1',port,timeout=20)
        try:
            connection.request('POST',path,body=raw,headers={'Content-Type':'application/json','Authorization':'Bearer '+self.token.decode('ascii')})
            response=connection.getresponse();body=response.read(65537)
            if response.status!=200 or len(body)>65536:raise ValueError('planning reader unavailable')
            def pairs(items):
                result={}
                for key,value in items:
                    if key in result:raise ValueError('duplicate reader field')
                    result[key]=value
                return result
            return json.loads(body,object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('invalid reader response')))
        finally:connection.close()

    def origin(self,dispatch,issue_id,*,message=None,session=None,stop=False):
        d=local('onboarding_drafts');d.identifier(dispatch);d.identifier(issue_id)
        result=self.request('origin',{'dispatch_id':dispatch})
        if (type(stop) is not bool or type(result) is not dict or set(result)!={'contract','dispatch_id','issue_id','message','signal','permitted','human_approval_inferred','origin'} or
                result['contract']!='codex-planning-origin.v1' or result['dispatch_id']!=dispatch or
                result['issue_id']!=issue_id or
                type(result['message']) is not str or len(result['message'].encode('utf-8'))>65536 or
                (message is not None and result['message']!=message) or
                (result['signal']!='stop' if stop else result['signal'] not in (None,'continue')) or
                result['permitted'] is not True or result['human_approval_inferred'] is not False):
            raise ValueError('planning origin unavailable')
        origin=d.verified(result['origin'])
        if session is not None and origin['source_session']!=session:raise ValueError('planning session differs')
        return origin

    def issue(self,dispatch,origin,issue_id):
        d=local('onboarding_drafts');d.identifier(dispatch);d.identifier(issue_id);origin=d.verified(origin)
        result=self.request('issue',{'dispatch_id':dispatch,'issue_id':issue_id})
        if (type(result) is not dict or set(result)!={'contract','dispatch_id','origin','permitted','issue'} or
                result['contract']!='codex-planning-issue.v1' or result['dispatch_id']!=dispatch or
                result['permitted'] is not True or result['origin']!=origin):
            raise ValueError('planning issue unavailable')
        issue=result['issue']
        if type(issue) is not dict or issue.get('id')!=issue_id:raise ValueError('planning issue identity differs')
        return issue
