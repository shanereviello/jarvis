import http.client
import importlib.util
import json
from pathlib import Path
import socket
import threading
import pytest

path=Path(__file__).resolve().parents[1]/'tools/rras_reporting/onboarding_runtime_http.py'
spec=importlib.util.spec_from_file_location('planning_runtime_http_fixture',path)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_private_api_rejects_untrusted_requests_without_dispatch():
    class Runtime:
        def __init__(self):self.calls=[]
        def dispatch(self,event):self.calls.append(event);return {'state':'running'}
        def status(self,dispatch):return {'state':'completed','dispatch':dispatch}
        def interrupt(self,dispatch,session):self.calls.append((dispatch,session));return {'state':'interrupt_requested'}
    with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    token=b'fixture-private-token-with-at-least-32-bytes';runtime=Runtime()
    server=m.server(runtime,token,('127.0.0.1',port),verify_stop=lambda event:event.get('verified') is True);worker=threading.Thread(target=server.serve_forever);worker.start()
    def request(auth,body='{}',path='/v1/planning/dispatch'):
        connection=http.client.HTTPConnection('127.0.0.1',port,timeout=5)
        try:
            connection.request('POST',path,body,{'Authorization':auth,'Content-Type':'application/json'})
            response=connection.getresponse();response.read();return response.status
        finally:connection.close()
    try:
        assert request('')==403 and runtime.calls==[]
        assert request('Bearer '+token.decode(),'{"a":1,"a":2}')==409 and runtime.calls==[]
        assert request('Bearer '+token.decode())==202 and runtime.calls==[{}]
        assert request('Bearer '+token.decode(),'{}','/v1/planning/interrupt')==409
        stop=json.dumps(dict(verified=True,stop_dispatch_id='stop',target_dispatch_id='target',session_id='session'))
        assert request('Bearer '+token.decode(),stop,'/v1/planning/interrupt')==202
        assert runtime.calls[-1]==('target','session')
        with pytest.raises(ValueError):m.server(runtime,token,('0.0.0.0',port))
    finally:server.shutdown();worker.join();server.server_close()
