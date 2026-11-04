"""Cloudflare Access verification; no header-only trust or alternate login route."""
import json
import re
import ssl
import threading
import time
import urllib.request
import jwt


class Denied(ValueError):
    pass


def strict_json(raw):
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise Denied('unavailable')
            result[key]=value
        return result
    return json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(Denied('unavailable')))


class AccessConfig:
    def __init__(self,issuer,audience,email,origin):
        if type(issuer) is not str or not re.fullmatch(r'https://[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.cloudflareaccess\.com',issuer):
            raise ValueError('explicit Cloudflare team issuer required')
        if type(audience) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,256}',audience):raise ValueError('explicit application audience required')
        if type(email) is not str or len(email)>254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):raise ValueError('single operator email required')
        if type(origin) is not str or not re.fullmatch(r'https://[a-z0-9](?:[a-z0-9.-]{0,250}[a-z0-9])?',origin):raise ValueError('exact HTTPS application origin required')
        hostname=origin.removeprefix('https://')
        if any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?',part) for part in hostname.split('.')) or '.' not in hostname:
            raise ValueError('application DNS hostname required')
        self.issuer=issuer;self.audience=audience;self.email=email.casefold();self.origin=origin;self.hostname=hostname


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise Denied('unavailable')


class Keys:
    """Fixed-team HTTPS keys, bounded cache, expiry and refresh rate; fail closed."""
    def __init__(self,config,loader=None,clock=time.monotonic):
        self.url=config.issuer+'/cdn-cgi/access/certs';self.loader=loader or self.fetch
        self.clock=clock;self.lock=threading.Lock();self.keys={};self.expires=0;self.attempt=None

    def fetch(self):
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect(),urllib.request.HTTPSHandler(context=ssl.create_default_context()))
        with opener.open(urllib.request.Request(self.url,headers={'Accept':'application/json'}),timeout=3) as response:
            if response.geturl()!=self.url or response.status!=200:raise Denied('unavailable')
            raw=response.read(128*1024+1)
        if len(raw)>128*1024:raise Denied('unavailable')
        return strict_json(raw)

    def get(self,kid):
        with self.lock:
            now=self.clock()
            if now<self.expires and kid in self.keys:return self.keys[kid]
            if self.attempt is not None and now-self.attempt<30:raise Denied('unavailable')
            self.attempt=now
            try:
                value=self.loader()
                if type(value) is not dict or type(value.get('keys')) is not list or not 1<=len(value['keys'])<=16:raise Denied('unavailable')
                keys={}
                for item in value['keys']:
                    if (type(item) is not dict or item.get('kty')!='RSA' or item.get('use','sig')!='sig' or item.get('alg','RS256')!='RS256' or
                            type(item.get('kid')) is not str or not re.fullmatch(r'[A-Za-z0-9._+/=-]{1,128}',item['kid']) or item['kid'] in keys or
                            any(key in item for key in ('d','p','q','dp','dq','qi','oth'))):raise Denied('unavailable')
                    key=jwt.PyJWK.from_dict(item,algorithm='RS256').key
                    if not 2048<=key.key_size<=8192:raise Denied('unavailable')
                    keys[item['kid']]=key
                self.keys=keys;self.expires=self.clock()+300
            except Exception:raise Denied('unavailable') from None
            if kid not in self.keys:raise Denied('unavailable')
            return self.keys[kid]


class Access:
    def __init__(self,config,keys=None):self.config=config;self.keys=keys or Keys(config)

    def verify(self,headers):
        try:
            def one(name):
                values=[v for k,v in headers if k.lower()==name]
                if len(values)!=1:return None
                return values[0].decode('ascii')
            host=one(b'host');origin=one(b'origin')
            if host not in (self.config.hostname,self.config.hostname+':443'):raise Denied('unavailable')
            # Duplicate origins are rejected even if decoding would yield None.
            origins=[v for k,v in headers if k.lower()==b'origin']
            if len(origins)>1 or (origins and origin!=self.config.origin):raise Denied('unavailable')
            token=one(b'cf-access-jwt-assertion')
            if token is None or not 1<=len(token)<=16384:raise Denied('unavailable')
            pieces=token.split('.')
            if len(pieces)!=3:raise Denied('unavailable')
            untrusted=strict_json(jwt.utils.base64url_decode(pieces[0]))
            strict_json(jwt.utils.base64url_decode(pieces[1]))
            if (untrusted.get('alg')!='RS256' or untrusted.get('typ','JWT')!='JWT' or
                    any(k in untrusted for k in ('crit','jku','jwk','x5u')) or
                    type(untrusted.get('kid')) is not str or not re.fullmatch(r'[A-Za-z0-9._+/=-]{1,128}',untrusted['kid'])):
                raise Denied('unavailable')
            claims=jwt.decode(token,self.keys.get(untrusted['kid']),algorithms=['RS256'],issuer=self.config.issuer,audience=self.config.audience,
                options={'require':['exp','iat','nbf','iss','aud','sub','email']},leeway=0)
            if (any(type(claims[k]) is not int for k in ('exp','iat','nbf')) or claims['exp']<=max(claims['iat'],claims['nbf']) or
                    type(claims['sub']) is not str or not 1<=len(claims['sub'])<=256 or
                    type(claims['email']) is not str or claims['email'].casefold()!=self.config.email):raise Denied('unavailable')
            return {'email':self.config.email,'subject':claims['sub']}
        except Exception:raise Denied('unavailable') from None
