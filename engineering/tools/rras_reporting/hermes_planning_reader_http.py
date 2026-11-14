"""Loopback-only native Jarvis planning reads from a protected n8n workflow."""
import http.client
import importlib.util
import json
from pathlib import Path
from urllib.parse import urlsplit


def local(name):
    spec=importlib.util.spec_from_file_location('hermes_planning_reader_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


class Reader:
    def __init__(self,origin_url,issue_url,app_id,token):
        local('onboarding_drafts').identifier(app_id)
        if type(token) is not bytes or not 32<=len(token)<=256 or not all(33<=x<=126 for x in token):
            raise ValueError('private native planning reader credential required')
        self.paths={}
        for kind,url in (('origin',origin_url),('issue',issue_url)):
            if type(url) is not str:raise ValueError('fixed native planning endpoint required')
            parsed=urlsplit(url)
            if (parsed.scheme!='http' or parsed.hostname!='127.0.0.1' or parsed.username or parsed.password or
                    parsed.query or parsed.fragment or parsed.port is None or not 1<=parsed.port<=65535 or
                    parsed.path!='/webhook/rras-jarvis-planning-'+kind+'-'+app_id):
                raise ValueError('fixed loopback native planning endpoint required')
            self.paths[kind]=(parsed.port,parsed.path)
        self.token=token

    def request(self,kind,value):
        raw=json.dumps(value,separators=(',',':'),allow_nan=False).encode()
        if len(raw)>16384:raise ValueError('bounded native planning request required')
        port,path=self.paths[kind];connection=http.client.HTTPConnection('127.0.0.1',port,timeout=20)
        try:
            connection.request('POST',path,body=raw,headers={'Content-Type':'application/json','Authorization':'Bearer '+self.token.decode('ascii')})
            response=connection.getresponse();body=response.read(65537)
            if response.status!=200 or len(body)>65536:raise ValueError('native planning reader unavailable')
            def unique(items):
                result={}
                for key,value in items:
                    if key in result:raise ValueError('duplicate native response field')
                    result[key]=value
                return result
            result=json.loads(body,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('invalid response')))
            if type(result) is not dict:raise ValueError('exact native planning response required')
            return result
        finally:connection.close()

    def origin(self,native):
        return self.request('origin',{'native':native})

    def issue(self,native,origin,issue_id):
        drafts=local('onboarding_drafts');drafts.identifier(issue_id);origin=drafts.verified(origin)
        result=self.request('issue',{'native':native,'issue_id':issue_id})
        if (type(result) is not dict or set(result)!={'contract','native','origin','issue','permitted'} or
                result['contract']!='hermes-planning-issue.v1' or result['native']!=native or
                result['origin']!=origin or result['permitted'] is not True or
                type(result['issue']) is not dict or result['issue'].get('id')!=issue_id):
            raise ValueError('independent native issue verification required')
        return result['issue']
