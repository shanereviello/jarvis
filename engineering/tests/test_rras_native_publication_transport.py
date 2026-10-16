import importlib.util
import json
from pathlib import Path
import subprocess
import pytest
from test_rras_native_publication import fixture

ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('transport',ROOT/'tools/rras_native/publication_transport.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

def run(argv):return subprocess.run(argv,capture_output=True,timeout=10)

def setup(fixture,tmp_path):
    remote=tmp_path/'remote.git';subprocess.run(['git','init','--bare','-q',str(remote)],check=True)
    fixture['policy']['repositories']['jarvis']['remote']=str(remote)
    prepared=m.local('publication').prepare(**fixture)
    return prepared,fixture['policy'],tmp_path/'receipt.json'

def test_push_and_durable_receipt(fixture,tmp_path):
    prepared,policy,receipt=setup(fixture,tmp_path)
    result=m.publish(prepared,policy,receipt,run)
    assert result['status']=='published' and result['remote_write_attempted']
    assert json.loads(receipt.read_text())['commit']==prepared['commit']
    assert not result['merge_authorized'] and not result['deploy_authorized']
    assert m.remote_commit(prepared,run)==prepared['commit']
    with pytest.raises(ValueError):m.publish(prepared,policy,receipt,run)

def test_lost_push_response_retains_unknown_and_forbids_retry(fixture,tmp_path):
    prepared,policy,receipt=setup(fixture,tmp_path)
    def lost(argv):
        answer=run(argv)
        if 'push' in argv:raise TimeoutError('secret-like raw diagnostic must not be saved')
        return answer
    result=m.publish(prepared,policy,receipt,lost)
    assert result['status']=='unknown' and result['remote_write_attempted']
    assert m.remote_commit(prepared,run)==prepared['commit']
    assert 'secret-like' not in receipt.read_text()
    with pytest.raises(ValueError):m.publish(prepared,policy,receipt,run)

@pytest.mark.parametrize('change',['remote','branch','dirty','commit'])
def test_tampering_refused_before_transport(fixture,tmp_path,change):
    prepared,policy,receipt=setup(fixture,tmp_path)
    if change=='remote':prepared['remote']='git@github.com:another/repo.git'
    if change=='branch':prepared['branch']='main'
    if change=='dirty':(Path(prepared['checkout'])/'calc.py').write_text('changed')
    if change=='commit':prepared['commit']='0'*40
    with pytest.raises(ValueError):m.publish(prepared,policy,receipt,run)
    assert not Path(str(receipt)+'.started').exists()

def test_existing_branch_is_never_adopted(fixture,tmp_path):
    prepared,policy,receipt=setup(fixture,tmp_path)
    subprocess.run(m.local('publication').push_argv(prepared),check=True,capture_output=True)
    result=m.publish(prepared,policy,receipt,run)
    assert result['status']=='unknown' and not result['remote_write_attempted']


def test_ssh_transport_drops_provider_credentials(monkeypatch):
    monkeypatch.setenv('RRAS_OPENAI_API_KEY','never-forward')
    monkeypatch.setenv('OPENAI_API_KEY','never-forward')
    monkeypatch.setenv('SSH_AUTH_SOCK','/operator/agent')
    seen={}
    def fake(argv,**kw):seen.update(kw);return None
    monkeypatch.setattr(m.subprocess,'run',fake)
    m.command(['/usr/bin/git','--version'])
    assert 'RRAS_OPENAI_API_KEY' not in seen['env'] and 'OPENAI_API_KEY' not in seen['env']
    assert seen['env']['SSH_AUTH_SOCK']=='/operator/agent'
    assert 'BatchMode=yes' in seen['env']['GIT_SSH_COMMAND']
