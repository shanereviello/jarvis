"""Fixed private transport for Jarvis planning; no retry or credential output."""
import http.client
import importlib.util
import json
from pathlib import Path
from urllib.parse import urlsplit


def local(name):
    spec=importlib.util.spec_from_file_location('hermes_planning_transport_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


class Transport:
    def __init__(self, origin, token):
        parsed=urlsplit(origin)
        if (parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or
                parsed.query or parsed.fragment or parsed.path not in ('','/') or type(token) is not bytes or
                not 32<=len(token)<=256 or not all(33<=item<=126 for item in token)):
            raise ValueError('protected planning transport required')
        self.origin,self.token=parsed,token

    def __call__(self, operation, frame):
        paths={'resolve':'/webhook/rras-jarvis-planning-resolve','submit':'/webhook/rras-jarvis-planning-submit'}
        if operation not in paths:raise ValueError('unknown planning transport operation')
        raw=json.dumps(frame,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
        if len(raw)>128*1024:raise ValueError('bounded planning frame required')
        cls=http.client.HTTPSConnection if self.origin.scheme=='https' else http.client.HTTPConnection
        connection=cls(self.origin.hostname,self.origin.port,timeout=75)
        try:
            connection.request('POST',paths[operation],body=raw,
                headers={'Content-Type':'application/json','Authorization':'Bearer '+self.token.decode('ascii')})
            response=connection.getresponse();body=response.read(131073)
            if response.status!=200 or len(body)>131072:raise ValueError('planning response unconfirmed')
            def pairs(items):
                result={}
                for key,value in items:
                    if key in result:raise ValueError('duplicate planning response field')
                    result[key]=value
                return result
            value=json.loads(body,object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('invalid response')))
            if type(value) is not dict:raise ValueError('exact planning response required')
            return value
        finally:connection.close()


def configured(path):
    protected=local('protected_config');value=protected.decode(path,require_root=True,maximum=65536)
    if (type(value) is not dict or set(value)!={'contract','origin','token_file','allow_create','allow_review'} or
            value['contract']!='hermes-planning-config.v1' or type(value['allow_create']) is not bool or
            type(value['allow_review']) is not bool):raise ValueError('exact protected planning configuration required')
    token=protected.read(value['token_file'],maximum=257,require_root=True).strip()
    return local('hermes_planning').Adapter(Transport(value['origin'],token),
        allow_create=value['allow_create'],allow_review=value['allow_review'])
