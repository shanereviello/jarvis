"""Authenticated private Jarvis planning bridge; no public ingress or retries."""
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json


def server(broker, peer_uid, token, address=('127.0.0.1',8768)):
    if (type(peer_uid) is not int or peer_uid <= 0 or type(token) is not bytes or not 32 <= len(token) <= 256 or
            not all(33 <= item <= 126 for item in token)):
        raise ValueError('dedicated planning peer and private credential required')
    if (type(address) is not tuple or len(address) != 2 or type(address[0]) is not str or type(address[1]) is not int or
            not 1 <= address[1] <= 65535 or not (ipaddress.ip_address(address[0]).is_loopback or ipaddress.ip_address(address[0]).is_private) or
            ipaddress.ip_address(address[0]).is_unspecified):
        raise ValueError('fixed private planning bind required')
    class Handler(BaseHTTPRequestHandler):
        def setup(self):super().setup();self.connection.settimeout(5)
        def log_message(self,*_):pass
        def reply(self,status,value):
            raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
            self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store')
            self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        def do_POST(self):
            if not hmac.compare_digest(self.headers.get('Authorization','').encode(),b'Bearer '+token):
                self.close_connection=True;self.reply(403,{'error':'planning access refused'});return
            try:
                if (self.path not in ('/webhook/rras-jarvis-planning-resolve','/webhook/rras-jarvis-planning-submit') or
                        self.headers.get('Transfer-Encoding') or self.headers.get('Content-Type')!='application/json'):
                    raise ValueError('exact planning request required')
                length=int(self.headers.get('Content-Length','-1'))
                if not 1<=length<=128*1024:raise ValueError('bounded planning request required')
                raw=self.rfile.read(length)
                if len(raw)!=length:raise ValueError('truncated request')
                def unique(items):
                    result={}
                    for key,value in items:
                        if key in result:raise ValueError('duplicate request field')
                        result[key]=value
                    return result
                frame=json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('invalid number')))
                value=broker.resolve(peer_uid,frame) if self.path.endswith('-resolve') else broker.submit(peer_uid,frame)
                self.reply(200,value)
            except Exception:
                self.close_connection=True;self.reply(409,{'error':'planning request refused or uncertain; inspect retained state'})
    return ThreadingHTTPServer(address,Handler)
