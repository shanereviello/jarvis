"""Authenticated private planning runtime API; no public ingress."""
import hmac
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import ipaddress
import json


def server(runtime,token,address=('127.0.0.1',8767),*,verify_stop=None):
    if type(token) is not bytes or not 32<=len(token)<=256 or not all(33<=x<=126 for x in token):
        raise ValueError('private planning bridge credential required')
    if (type(address) is not tuple or len(address)!=2 or type(address[0]) is not str or type(address[1]) is not int or
            not 1<=address[1]<=65535 or not (ipaddress.ip_address(address[0]).is_loopback or ipaddress.ip_address(address[0]).is_private) or
            ipaddress.ip_address(address[0]).is_unspecified):raise ValueError('fixed private bind required')
    class Handler(BaseHTTPRequestHandler):
        def setup(self):super().setup();self.connection.settimeout(5)
        def log_message(self,*args):pass
        def reply(self,status,value):
            raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
            self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store')
            self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        def allowed(self):
            if not hmac.compare_digest(self.headers.get('Authorization','').encode(),b'Bearer '+token):
                self.close_connection=True;self.reply(403,{'error':'planning access refused'});return False
            return True
        def do_GET(self):
            if not self.allowed():return
            try:
                if not self.path.startswith('/v1/planning/runs/'):raise ValueError('unknown route')
                self.reply(200,runtime.status(self.path[len('/v1/planning/runs/'):]))
            except Exception:self.reply(409,{'error':'planning status refused or unavailable'})
        def do_POST(self):
            if not self.allowed():return
            try:
                if self.path not in ('/v1/planning/dispatch','/v1/planning/interrupt') or self.headers.get('Transfer-Encoding') or self.headers.get('Content-Type')!='application/json':
                    raise ValueError('exact request required')
                length=int(self.headers.get('Content-Length','-1'))
                if not 1<=length<=128*1024:raise ValueError('bounded request required')
                raw=self.rfile.read(length)
                if len(raw)!=length:raise ValueError('truncated request')
                def unique(items):
                    result={}
                    for key,value in items:
                        if key in result:raise ValueError('duplicate field')
                        result[key]=value
                    return result
                event=json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('invalid number')))
                if self.path=='/v1/planning/dispatch':self.reply(202,runtime.dispatch(event))
                else:
                    if not callable(verify_stop) or verify_stop(event) is not True:raise ValueError('verified stop required')
                    result=runtime.interrupt(event['target_dispatch_id'],event['session_id'])
                    if result.get('state')!='interrupt_requested':raise ValueError('stop request unconfirmed')
                    self.reply(202,dict(dispatch=event['stop_dispatch_id'],state='completed',
                        result='Stop requested; the planning turn has not yet reported its final state.'))
            except Exception:
                self.close_connection=True;self.reply(409,{'error':'planning request refused or uncertain; retain dispatch identity'})
    return ThreadingHTTPServer(address,Handler)
