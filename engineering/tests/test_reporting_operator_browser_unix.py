import importlib.util
import os
from pathlib import Path
import tempfile
import threading
import pytest

path=Path(__file__).resolve().parents[1]/'tools/rras_reporting/onboarding_operator_browser_unix.py'
spec=importlib.util.spec_from_file_location('operator_browser_unix_fixture',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_private_bridge_preserves_headers_and_exposes_only_attestation():
    calls=[]
    class Browser:
        def begin(self,headers,review,comment):calls.append((headers,review,comment));return {'challenge':'fixture'}
        def confirm(self,headers,challenge,statement):calls.append((headers,challenge,statement));return {'execution_authorized':False}
    h=[(b'host',b'example.test'),(b'origin',b'https://example.test'),(b'cf-access-jwt-assertion',b'fixture')]
    broker=module.Broker(os.getuid(),Browser())
    transport=module.local('onboarding_broker_unix')
    with tempfile.TemporaryDirectory(prefix='rras-operator-',dir='/tmp') as raw:
        socket=Path(raw)/'operator.sock';stop=threading.Event()
        with transport.server(socket,broker) as server:
            def serve():
                while not stop.is_set():server.serve_once()
            worker=threading.Thread(target=serve);worker.start()
            try:
                client=module.Client(socket,os.getuid())
                assert client.unix.DEADLINE_SECONDS==60
                assert client.begin(h,'review','comment')=={'challenge':'fixture'}
                assert not client.confirm(h,'fixture','statement')['execution_authorized']
                with pytest.raises(ValueError):transport.unix().call(socket,os.getuid(),{'operation':'project_submit'})
                assert calls==[(h,'review','comment'),(h,'fixture','statement')]
            finally:stop.set();worker.join(5)
            assert not worker.is_alive()
