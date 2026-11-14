import importlib.util
import os
from pathlib import Path
import tempfile
import threading
import pytest

path=Path(__file__).resolve().parents[1]/'tools/rras_reporting/onboarding_broker_unix.py'
spec=importlib.util.spec_from_file_location('planning_broker_unix_fixture',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_unix_transport_supplies_kernel_peer_and_refuses_registration():
    seen=[]
    class Broker:
        grants={os.getuid():{}}
        def dispatch(self,peer,message):
            seen.append(peer)
            if message!={'operation':'draft.project'}:raise ValueError('refused')
            return {'execution_authorized':False}
    with tempfile.TemporaryDirectory(prefix='rras-planning-',dir='/tmp') as raw:
        path=Path(raw)/'broker.sock';stop=threading.Event()
        with module.server(path,Broker()) as server:
            def run():
                while not stop.is_set():server.serve_once()
            worker=threading.Thread(target=run);worker.start()
            try:
                assert module.unix().call(path,os.getuid(),{'operation':'draft.project'})=={'execution_authorized':False}
                with pytest.raises(ValueError):module.unix().call(path,os.getuid(),{'operation':'register'})
            finally:stop.set();worker.join(5)
            assert not worker.is_alive()
    assert seen==[os.getuid(),os.getuid()]
