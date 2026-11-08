"""Actual private HTTP transport sends only bounded read parameters, not OAuth."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import threading
import pytest

ROOT=Path(__file__).resolve().parents[1]/'tools/rras_reporting'
spec=importlib.util.spec_from_file_location('observer_http_test',ROOT/'linear_observer_http.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_actual_http_read_has_header_auth_no_arbitrary_query_and_no_redirect():
    seen=[];status=[200]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            seen.append((body,self.headers.get('Authorization')))
            self.send_response(status[0]);self.send_header('Location','https://elsewhere.invalid');self.end_headers()
            self.wfile.write(b'{"data":{"synthetic":true}}')
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        query=m.reader('http://127.0.0.1:'+str(server.server_port)+'/webhook/rras-history-linear-read-fixture',b'x'*64)
        request=dict(operation='issues',object_id='selected',query='never forward arbitrary queries',variables=dict(after='cursor'))
        assert query(request)==dict(data=dict(synthetic=True))
        assert seen==[(dict(operation='issues',object_id='selected',after='cursor'),'Bearer '+'x'*64)]
        status[0]=302
        with pytest.raises(ValueError):query(request)
        assert len(seen)==2
    finally:server.shutdown();server.server_close();thread.join(timeout=3)


@pytest.mark.parametrize('url',['https://user:secret@host/webhook/rras-history-linear-read-id',
    'http://host/other','https://host/webhook/rras-history-linear-read-id?token=secret','file:///tmp/source'])
def test_credential_bearing_redirected_or_arbitrary_endpoints_refused(url):
    with pytest.raises(ValueError):m.reader(url,b'x'*64)
