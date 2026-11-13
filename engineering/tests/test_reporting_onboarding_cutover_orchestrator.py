import importlib.util
import os
from pathlib import Path

import pytest

path = Path(__file__).resolve().parents[1]/'tools/rras_reporting/onboarding_cutover_orchestrator.py'
spec = importlib.util.spec_from_file_location('cutover_orchestrator_fixture',path)
module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_orchestrator_refuses_nonroot_before_starting_processes():
    if os.getuid() == 0:pytest.skip('requires unprivileged fixture')
    called = []
    with pytest.raises(ValueError,match='root orchestrator'):
        module.run('/not-a-config',{},popen=lambda *args,**kwargs:called.append(args))
    assert not called


@pytest.mark.parametrize('peer_success',[True,False])
def test_orchestrator_runs_once_and_preserves_failed_outcome(tmp_path,monkeypatch,peer_success):
    import hashlib,json,socket
    from types import SimpleNamespace
    runtime = module.local('codex_runtime')
    plan = {'fixture':True};sha = hashlib.sha256(runtime.encoded(plan)).hexdigest()
    config = {'broker_socket':str(tmp_path/'broker.sock'),'transition':{'plan':plan,'old':{},'new':{}}}
    config_path = tmp_path/'config';config_path.write_text('{}')
    adapter = SimpleNamespace(pw_uid=1234,pw_gid=1234)
    modules = {'onboarding_cutover_entry':SimpleNamespace(configuration=lambda _:(config,adapter,None)),
        'protected_config':SimpleNamespace(decode=lambda *_,**__:config),'codex_runtime':runtime}
    monkeypatch.setattr(module,'local',lambda name:modules[name])
    monkeypatch.setattr(module.os,'getuid',lambda:0);monkeypatch.setattr(module.os,'geteuid',lambda:0)
    original_lstat = Path.lstat
    def lstat(self):
        info = original_lstat(self)
        if self == config_path:return SimpleNamespace(st_mode=0o100640,st_uid=0,st_gid=1234,st_nlink=1)
        if str(self) == config['broker_socket']:
            return SimpleNamespace(st_mode=info.st_mode,st_uid=0,st_gid=1234)
        return info
    monkeypatch.setattr(Path,'lstat',lstat)
    listener = socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
    processes = []
    class Process:
        def __init__(self,role):self.role=role;self.returncode=None;self.terminated=False
        def poll(self):return self.returncode
        def communicate(self,timeout):
            self.returncode = 0 if self.role == 'root' or peer_success else 1
            result = {'completed':True,'plan_sha256':sha,'models_started':0,'runtime_started':False} if self.role == 'root' else {'cutover_complete':True,'plan_sha256':sha,'models_started':0}
            return json.dumps(result),''
        def send_signal(self,_):self.terminated=True;self.returncode=-1
        def wait(self,timeout):return self.returncode
    def popen(*_,**__):
        role = 'root' if not processes else 'peer'
        if role == 'root':listener.bind(config['broker_socket']);Path(config['broker_socket']).chmod(0o660)
        process = Process(role);processes.append(process);return process
    try:
        if peer_success:
            assert module.run(config_path,config,popen=popen)['completed']
        else:
            with pytest.raises(ValueError,match='journal-owner'):
                module.run(config_path,config,popen=popen)
            assert processes[0].terminated
        assert len(processes) == 2
    finally:listener.close()
