"""Synthetic route tooling fixed scope and privilege refusal; no Docker mutations."""
from pathlib import Path
import pytest
from test_history_web import web

module=web('connector_check')


def test_unprivileged_run_refused_before_docker_or_files():
    with pytest.raises(ValueError,match='explicit sudo'):module.run()


def test_client_pinned_isolated_identity_without_mounts_credentials_or_pull():
    command=module.client_command()
    assert command[command.index('--network')+1]=='jarvis-net'
    assert command[command.index('--user')+1]=='61167:61167'
    assert '--pull=never' in command and '--read-only' in command and '--cap-drop=ALL' in command
    assert '--security-opt=no-new-privileges:true' in command and module.IMAGE in command
    assert not any(item in ('-v','--volume','--mount','--privileged','--env-file','-e') for item in command)
    assert command[-1]==module.CLIENT


def test_embedded_programs_compile_and_have_no_directory_server():
    compile(module.SERVER,'fixture-server','exec');compile(module.CLIENT,'fixture-client','exec')
    assert 'SimpleHTTPRequestHandler' not in module.SERVER
    assert 'signal.alarm(45)' in module.SERVER and 'prctl(1,signal.SIGTERM' in module.SERVER


def test_cleanup_never_stops_unlabelled_container(monkeypatch):
    calls=[];monkeypatch.setattr(module,'absent',lambda:False)
    monkeypatch.setattr(module,'checked',lambda argv,**kwargs:calls.append(argv) or b'unrelated\n')
    with pytest.raises(ValueError,match='label differs'):module.cleanup_container()
    assert len(calls)==1 and calls[0][1]=='inspect'


@pytest.mark.parametrize('groups,allowed',[([],True),([61167],True),([61167,0],False),([0],False),([61167,995],False)])
def test_actual_client_guard_allows_only_its_primary_group(monkeypatch,groups,allowed):
    import io,builtins,os,sys
    for name in ('getuid','geteuid','getgid','getegid'):monkeypatch.setattr(os,name,lambda:61167)
    monkeypatch.setattr(os,'getgroups',lambda:groups)
    monkeypatch.setattr(sys,'stdin',io.StringIO('{"nonce":"synthetic"}'))
    monkeypatch.setattr(os,'environ',{'PATH':'/usr/bin:/bin','HOME':'/nonexistent','LANG':'C.UTF-8'})
    status='NoNewPrivs:\t1\n'+''.join(name+':\t0\n' for name in ('CapInh','CapPrm','CapEff','CapBnd','CapAmb'))
    def read(path,*args,**kwargs):
        assert path=='/proc/self/status';return io.StringIO(status)
    monkeypatch.setattr(builtins,'open',read)
    prefix=module.CLIENT.split('for host,wanted',1)[0]
    if allowed:exec(compile(prefix,'actual-client-guard','exec'),{})
    else:
        with pytest.raises(ValueError,match='client identity differs'):exec(compile(prefix,'actual-client-guard','exec'),{})
