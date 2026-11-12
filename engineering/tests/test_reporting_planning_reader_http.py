import importlib.util
import json
from http.server import BaseHTTPRequestHandler,HTTPServer
from pathlib import Path
import threading
import pytest

path=Path(__file__).resolve().parents[1]/'tools/rras_reporting/planning_reader_http.py'
spec=importlib.util.spec_from_file_location('planning_reader_http_fixture',path)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def uid(n):return f'00000000-0000-4000-8000-{n:012d}'


def test_reader_binds_dispatch_origin_issue_and_private_endpoint():
    token=b'fixture-private-token-with-at-least-32-bytes'
    origin=dict(organization_id=uid(1),team_id=uid(2),project_id=uid(3),project_identifier=uid(3),
        project_url='https://linear.app/fixture/project/example',scope=dict(kind='repository',id='jarvis'),
        source_session=uid(4),source_actor=uid(5),agent='codex')
    issue=dict(organization_id=uid(1),team_id=uid(2),project_id=uid(3),id=uid(7),identifier='ENG-1',url='https://linear.app/fixture/issue/ENG-1')
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            if self.headers.get('Authorization')!='Bearer '+token.decode():self.send_response(403);self.end_headers();return
            value=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            result=dict(permitted=True,dispatch_id=value['dispatch_id'],origin=origin)
            if self.path.startswith('/webhook/rras-planning-origin-'):
                result.update(contract='codex-planning-origin.v1',human_approval_inferred=False)
            else:result.update(contract='codex-planning-issue.v1',issue=issue)
            body=json.dumps(result).encode();self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    server=HTTPServer(('127.0.0.1',0),Handler);worker=threading.Thread(target=server.serve_forever);worker.start()
    try:
        base=f'http://127.0.0.1:{server.server_port}/webhook/rras-planning-'
        reader=m.Reader(base+'origin-'+uid(9),base+'issue-'+uid(9),uid(9),token)
        assert reader.origin(uid(6))==origin
        assert reader.issue(uid(6),origin,uid(7))==issue
        with pytest.raises(ValueError):reader.issue(uid(6),dict(origin,source_actor=uid(8)),uid(7))
        with pytest.raises(ValueError):m.Reader(base.replace('127.0.0.1','example.com')+'origin-'+uid(9),base+'issue-'+uid(9),uid(9),token)
    finally:server.shutdown();worker.join();server.server_close()
