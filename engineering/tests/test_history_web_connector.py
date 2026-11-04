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
    assert command[command.index('--user')+1]=='61166:61166'
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
