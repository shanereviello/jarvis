import importlib.util
import json
from pathlib import Path
from unittest.mock import patch
import pytest
from test_rras_native_publication import fixture
from test_rras_native_publication_transport import setup

ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('handoff',ROOT/'tools/rras_native/publication_handoff.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

def package(fixture,tmp_path):
    a=m.local('activity');prepared,policy,_=setup(fixture,tmp_path)
    policy_path=tmp_path/'policy.json';a.absent(policy_path,a.encoded(policy))
    prepared['policy_sha256']=a.digest(policy_path.read_bytes())
    prepared_path=tmp_path/'prepared.json';a.absent(prepared_path,a.encoded(prepared))
    custody=m.local('publication_custody');launch=m.local('approved_launch')
    original=m.local
    with patch.object(m.os,'geteuid',return_value=0),\
         patch.object(custody,'root_bytes',side_effect=lambda p,limit:Path(p).read_bytes()),\
         patch.object(launch,'trusted',side_effect=lambda p:Path(p)),\
         patch.object(m,'local',side_effect=lambda n:{'publication_custody':custody,'approved_launch':launch}.get(n) or original(n)):
        record=m.export(prepared_path,policy_path,tmp_path/'handoff')
    return record,tmp_path/'handoff'

def root_reads():
    custody=m.local('publication_custody')
    return custody,patch.object(custody,'root_bytes',side_effect=lambda p,limit:Path(p).read_bytes())

@pytest.fixture(autouse=True)
def fixture_workspace_ancestors(monkeypatch):
    # These legacy local transport fixtures live under /tmp. Real parent checks
    # are exercised independently in test_publication_workspace.py.
    monkeypatch.setattr(m, 'workspace_path', lambda record, path=None: Path(path))


def test_bundle_operator_import_and_local_publication(fixture,tmp_path):
    record,path=package(fixture,tmp_path)
    assert path.stat().st_mode&0o777==0o555
    assert 'checkout' not in record['prepared']
    custody,reader=root_reads();original=m.local
    with reader,patch.object(m,'local',side_effect=lambda n:custody if n=='publication_custody' else original(n)):
        prepared=m.import_review(path,tmp_path/'operator')
        assert Path(prepared['checkout']).stat().st_uid==m.os.getuid()
        result=m.publish(path,tmp_path/'operator')
        assert result['status']=='published'
        with pytest.raises(ValueError):m.publish(path,tmp_path/'operator')

@pytest.mark.parametrize('change',['identity','bundle','existing','dirty'])
def test_handoff_refusals(fixture,tmp_path,change):
    record,path=package(fixture,tmp_path);custody,reader=root_reads();original=m.local
    with reader,patch.object(m,'local',side_effect=lambda n:custody if n=='publication_custody' else original(n)):
        if change=='identity':
            with patch.object(m.os,'getuid',return_value=996),pytest.raises(ValueError):m.import_review(path,tmp_path/'operator')
        elif change=='bundle':
            (path/'review.bundle').chmod(0o600);(path/'review.bundle').write_bytes(b'changed')
            with pytest.raises(ValueError):m.import_review(path,tmp_path/'operator')
        elif change=='existing':
            (tmp_path/'operator').mkdir()
            with pytest.raises(ValueError):m.import_review(path,tmp_path/'operator')
        else:
            m.import_review(path,tmp_path/'operator')
            (tmp_path/'operator/repo/calc.py').write_text('changed')
            with pytest.raises(ValueError):m.publish(path,tmp_path/'operator')

def test_handoff_probe_cannot_target_production_paths():
    probe=m.local('probe_publication_handoff')
    for path in ('/srv/git/jarvis','/var/lib/rras-engineering','/tmp/rras-publication-operator-'+'a'*32):
        with pytest.raises(ValueError):probe.fixture_root(path)
    with patch.object(probe.os,'geteuid',return_value=1000),pytest.raises(ValueError):probe.prepare('/var/lib/rras-publication-operator-'+'a'*32,'/invalid')
