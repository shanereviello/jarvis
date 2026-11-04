"""Committed stdlib root-helper emission and no-root/no-action boundary checks."""
from pathlib import Path
import hashlib
import subprocess
import pytest
from test_history_web import web,TOOLS

emitter=web('protected_package_check')


def repository(tmp_path):
    repo=tmp_path/'repo';folder=repo/'engineering/tools/rras_history_web';folder.mkdir(parents=True)
    for name in ('production_package.py','protected_package_probe.py','stage_protected_package_check.py'):
        (folder/name).write_bytes((TOOLS/name).read_bytes())
    env={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','LANG':'C.UTF-8','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null'}
    def git(*args):return subprocess.check_output(['/usr/bin/git','-C',str(repo),*args],stderr=subprocess.PIPE,env=env).decode().strip()
    git('init');git('add','.');git('-c','user.name=Fixture','-c','user.email=fixture@example.test','commit','-m','Synthetic helper input')
    return repo,git('rev-parse','HEAD')


def test_emits_exact_committed_probe_and_refuses_root_action_as_user(tmp_path):
    source,commit=repository(tmp_path);path=tmp_path/'helper.py'
    result=emitter.emit(source,commit,path)
    assert result['helper_sha256']==hashlib.sha256(path.read_bytes()).hexdigest()
    namespace={'__name__':'fixture_helper'};exec(compile(path.read_bytes(),str(path),'exec'),namespace)
    assert result['probe_sha256']==hashlib.sha256(namespace['PROBE_BYTES']).hexdigest()
    with pytest.raises(ValueError,match='explicit sudo'):namespace['check']('/not-opened','0'*64)


def test_working_tree_probe_changes_do_not_replace_committed_bytes(tmp_path):
    source,commit=repository(tmp_path);probe=source/'engineering/tools/rras_history_web/protected_package_probe.py'
    original=probe.read_bytes();probe.write_bytes(b'raise RuntimeError("uncommitted")\n')
    result=emitter.emit(source,commit,tmp_path/'helper.py')
    assert result['probe_sha256']==hashlib.sha256(original).hexdigest()


def test_wrong_tooling_head_refused_before_output(tmp_path):
    source,commit=repository(tmp_path);path=tmp_path/'helper.py'
    with pytest.raises(ValueError):emitter.emit(source,'0'*40,path)
    assert not path.exists()


def test_probe_refuses_operator_before_file_or_network_reads():
    probe=web('protected_package_probe')
    with pytest.raises(ValueError,match='fixed isolated probe'):probe.run('/not-opened','/not-opened')
