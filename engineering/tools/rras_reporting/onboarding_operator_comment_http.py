"""Protected loopback transport for the inactive n8n operator comment reader."""
import http.client
import importlib.util
import json
from pathlib import Path
from urllib.parse import urlsplit


def local(name):
    spec=importlib.util.spec_from_file_location('operator_comment_http_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


class Transport:
    def __init__(self,url,app_id,token):
        local('onboarding_drafts').identifier(app_id)
        if type(token) is not bytes or not 32<=len(token)<=256 or not all(33<=x<=126 for x in token):raise ValueError('private operator credential required')
        p=urlsplit(url)
        if (p.scheme!='http' or p.hostname!='127.0.0.1' or p.username or p.password or p.query or p.fragment or
                p.port is None or p.path!='/webhook/rras-operator-comment-'+app_id):
            raise ValueError('fixed loopback operator endpoint required')
        self.port,self.path,self.token=p.port,p.path,token

    def __call__(self,request):
        if (type(request) is not dict or set(request)!={'query','variables'} or
                request['query']!=local('onboarding_linear_comment_reader').QUERY or
                type(request['variables']) is not dict or set(request['variables'])!={'id'}):
            raise ValueError('fixed native comment query required')
        comment_id=request['variables']['id'];local('onboarding_drafts').identifier(comment_id)
        raw=json.dumps({'comment_id':comment_id},separators=(',',':')).encode()
        connection=http.client.HTTPConnection('127.0.0.1',self.port,timeout=20)
        try:
            connection.request('POST',self.path,body=raw,headers={'Content-Type':'application/json','Authorization':'Bearer '+self.token.decode('ascii')})
            response=connection.getresponse();body=response.read(65537)
            if response.status!=200 or len(body)>65536:raise ValueError('operator reader unavailable')
            def pairs(items):
                result={}
                for key,value in items:
                    if key in result:raise ValueError('duplicate operator reader field')
                    result[key]=value
                return result
            result=json.loads(body,object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('invalid response')))
            if type(result) is not dict or set(result)!={'permitted','data'} or result['permitted'] is not True or type(result['data']) is not dict:
                raise ValueError('operator reader refused')
            return {'data':result['data']}
        finally:connection.close()
