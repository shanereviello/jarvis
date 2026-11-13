import importlib.util
import json
from pathlib import Path
import threading
from http.server import BaseHTTPRequestHandler,HTTPServer

import pytest
from test_reporting_hermes_planning import fixture
from test_reporting_n8n_codex import uid


path=Path(__file__).resolve().parents[1]/'tools/rras_reporting/hermes_planning_create_http.py'
spec=importlib.util.spec_from_file_location('hermes_create_http_test',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_private_creator_checks_native_response_without_retry():
    native,_,_=fixture();calls=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])));calls.append(body)
            raw=json.dumps(dict(contract='hermes-planning-create.v1',native=body['native'],created=True,issue_id=uid(7))).encode()
            self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    server=HTTPServer(('127.0.0.1',0),Handler);worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    try:
        creator=module.Creator('http://127.0.0.1:'+str(server.server_port)+'/webhook/rras-jarvis-planning-create-'+uid(9),uid(9),b'x'*32)
        assert creator.create(native,'PLAN-1',dict(title='a',description='b'))==uid(7)
        assert len(calls)==1 and calls[0]['native']==native
        with pytest.raises(ValueError):module.Creator('http://example.com/webhook/rras-jarvis-planning-create-'+uid(9),uid(9),b'x'*32)
    finally:server.shutdown();worker.join();server.server_close()
