import http.server
import importlib.util
import json
from pathlib import Path
import threading
import pytest

path=Path(__file__).resolve().parents[1]/'tools/rras_reporting/planning_issue_create_http.py'
spec=importlib.util.spec_from_file_location('planning_create_http_fixture',path)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def uid(n):return f'00000000-0000-4000-8000-{n:012d}'


def test_creator_is_loopback_only_and_requires_exact_dispatch_result():
    token=b'fixture-private-token-with-at-least-32-bytes';requests=[]
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            assert self.headers['Authorization']=='Bearer '+token.decode()
            data=json.loads(self.rfile.read(int(self.headers['Content-Length'])));requests.append(data)
            raw=json.dumps(dict(contract='codex-planning-create.v1',dispatch_id=data['dispatch_id'],created=True,issue_id=uid(3))).encode()
            self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    server=http.server.HTTPServer(('127.0.0.1',0),Handler);worker=threading.Thread(target=server.serve_forever);worker.start()
    try:
        url=f'http://127.0.0.1:{server.server_port}/webhook/rras-planning-create-{uid(1)}'
        creator=m.Creator(url,uid(1),token)
        assert creator.create(uid(2),'PLAN-01',dict(title='Fixture',description='Fixture'))==uid(3)
        assert len(requests)==1
        with pytest.raises(ValueError):m.Creator(url.replace('127.0.0.1','example.com'),uid(1),token)
    finally:server.shutdown();worker.join();server.server_close()
