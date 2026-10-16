import importlib.util
import json
from pathlib import Path
from unittest.mock import patch
import pytest

ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('custody',ROOT/'tools/rras_native/publication_custody.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

def test_loader_refuses_nonroot_before_reading(tmp_path):
    with patch.object(m.os,'geteuid',return_value=1000),patch.object(m,'root_bytes') as read:
        with pytest.raises(ValueError):m.load(tmp_path)
        read.assert_not_called()

@pytest.mark.parametrize('tamper',[None,'hash','path','branch'])
def test_loader_hashes_members_and_run_assignment(tmp_path,tamper):
    a=m.local('activity');root=tmp_path/'custody';run_id='b'*32
    objects={'review':{},'host-result':dict(authorization_id='a'*32,run_id=run_id),
             'evidence':{'export':{'export_id':'e'*64}},'manifest':{}}
    data={root/(k+'.json'):a.encoded(v) for k,v in objects.items()}
    data[root/'artifacts/changes.patch']=b'patch'
    receipt=dict(authorization_id='a'*32,assigned_branch='codex/task-'+run_id,export_id='e'*64,
                 files={str(p.relative_to(root)):a.digest(v) for p,v in data.items()})
    if tamper=='hash':data[root/'artifacts/changes.patch']=b'changed'
    if tamper=='path':receipt['files']['../bad']='bad'
    if tamper=='branch':receipt['assigned_branch']='main'
    data[root/'capture.json']=a.encoded(receipt)
    with patch.object(m.os,'geteuid',return_value=0),patch.object(m,'root_bytes',side_effect=lambda p,limit:data[p]):
        if tamper:
            with pytest.raises(ValueError):m.load(root)
        else:
            result=m.load(root)
            assert result['files']=={'changes.patch':b'patch'}
            assert result['assigned_branch']=='codex/task-'+run_id

def test_workflow_probe_refuses_nonroot_before_host_actions():
    probe=m.local('probe_publication_workflow')
    with patch.object(probe.os,'geteuid',return_value=1000),patch.object(probe,'local') as imported:
        with pytest.raises(ValueError):probe.probe()
        imported.assert_not_called()

def test_complete_workflow_fixture_with_permission_checks_mocked(tmp_path):
    # Real Git/capture/hash/commit/transport; this source test does not establish
    # root ownership, UID separation or host service state. Operator probe does.
    probe=m.local('probe_publication_workflow')
    a=m.local('activity');launch=m.local('approved_launch');cap=m.local('publication_capture')
    custody=m.local('publication_custody');transport=m.local('publication_transport')
    modules={'activity':a,'approved_launch':launch,'publication_capture':cap,
             'publication_custody':custody,'publication_transport':transport}
    original_cap_local=cap.local;original_custody_local=custody.local
    with patch.object(probe.os,'geteuid',return_value=0),patch.object(probe.os,'chown'),\
         patch.object(probe,'Path',side_effect=lambda p:tmp_path if p=='/var/lib' else Path(p)),\
         patch.object(probe,'local',side_effect=modules.__getitem__),\
         patch.object(launch,'trusted',side_effect=lambda p:Path(p)),patch.object(launch,'slot'),\
         patch.object(cap,'local',side_effect=lambda name:launch if name=='approved_launch' else original_cap_local(name)),\
         patch.object(cap,'worker_bytes',side_effect=lambda p,limit:Path(p).read_bytes()),\
         patch.object(custody,'local',side_effect=lambda name:launch if name=='approved_launch' else original_custody_local(name)),\
         patch.object(custody,'root_bytes',side_effect=lambda p,limit:Path(p).read_bytes()):
        result=probe.probe()
    assert result['success'] and len(result['cases'])==7
    assert not result['network_used'] and not result['github_tested']
