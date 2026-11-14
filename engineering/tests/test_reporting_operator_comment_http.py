import importlib.util
import json
from http.server import BaseHTTPRequestHandler,HTTPServer
from pathlib import Path
import threading
import pytest
from test_reporting_n8n_codex import uid

path=Path(__file__).resolve().parents[1]/'tools/rras_reporting/onboarding_operator_comment_http.py'
spec=importlib.util.spec_from_file_location('operator_comment_http_fixture',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_loopback_reader_uses_exact_query_and_private_header():
    app=uid(4);comment=uid(5);token=b'x'*32;seen=[]
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            seen.append((self.path,self.headers.get('Authorization'),json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
            body=json.dumps({'permitted':True,'data':{'comment':{'id':comment}}}).encode()
            self.send_response(200);self.end_headers();self.wfile.write(body)
        def log_message(self,*_):pass
    server=HTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        url=f'http://127.0.0.1:{server.server_port}/webhook/rras-operator-comment-{app}'
        transport=module.Transport(url,app,token)
        request={'query':module.local('onboarding_linear_comment_reader').QUERY,'variables':{'id':comment}}
        assert transport(request)=={'data':{'comment':{'id':comment}}}
        assert seen==[(f'/webhook/rras-operator-comment-{app}','Bearer '+token.decode(),{'comment_id':comment})]
        with pytest.raises(ValueError):transport({'query':'mutation{}','variables':{'id':comment}})
        with pytest.raises(ValueError):module.Transport(url.replace('127.0.0.1','192.168.1.1'),app,token)
        with pytest.raises(ValueError):module.Transport(f'http://127.0.0.1:0/webhook/rras-operator-comment-{app}',app,token)
    finally:server.shutdown();thread.join();server.server_close()
