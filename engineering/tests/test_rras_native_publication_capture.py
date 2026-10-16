import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import pytest

ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('capture',ROOT/'tools/rras_native/publication_capture.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

def test_capture_requires_root_and_exact_authorization(tmp_path):
    with patch.object(m.os,'geteuid',return_value=1000),pytest.raises(ValueError):m.capture(tmp_path,'a'*32,tmp_path/'out')
    with patch.object(m.os,'geteuid',return_value=0),pytest.raises(ValueError):m.capture(tmp_path,'../bad',tmp_path/'out')

def test_reader_rejects_symlink_or_writable_ancestor(tmp_path):
    with pytest.raises(ValueError):m.worker_bytes(tmp_path/'not-present',100)

def test_capture_copies_exact_bytes_and_refuses_changed_artifact(tmp_path):
    a=m.local('activity');auth='a'*32;state=tmp_path/'state';state.mkdir();work=tmp_path/'work'
    review={'request':{'task_id':'TASK-test'},'submission_id':'submission'};review_id=a.digest(a.encoded(review))
    link=dict(authorization_id=auth,review_id=review_id,submission_id='submission',run_id='b'*32,work=str(work))
    result={**link,'service_exit':0,'host_stop_verified':True}
    a.absent(state/(auth+'.result.json'),a.encoded(result));a.absent(state/(auth+'.launch.json'),a.encoded(link))
    data=b'patch';manifest={'files':{'changes.patch':{'sha256':a.digest(data),'size_bytes':len(data)}}}
    export_id=a.digest(a.encoded(manifest));export=work/'index/TASK-test/exports'/export_id
    evidence={'export':{'export_id':export_id,'path':str(export)}}
    reads={work/'evidence.json':a.encoded(evidence),export/'manifest.json':a.encoded(manifest),export/'changes.patch':data}
    calls=[]
    launch=SimpleNamespace(trusted=lambda p:Path(p),slot=lambda:calls.append('stop'))
    approval=SimpleNamespace(read_review=lambda state,ident:review)
    modules={'activity':a,'approved_launch':launch,'approval':approval}
    with patch.object(m.os,'geteuid',return_value=0),patch.object(m,'local',side_effect=modules.__getitem__),patch.object(m,'worker_bytes',side_effect=lambda p,limit:reads[p]):
        out=tmp_path/'custody';r=m.capture(state,auth,out)
        assert calls==['stop','stop'] and r['assigned_branch']=='codex/task-'+'b'*32
        assert (out/'artifacts/changes.patch').read_bytes()==data
        reads[export/'changes.patch']=b'changed'
        with pytest.raises(ValueError):m.capture(state,auth,tmp_path/'bad')
        assert not (tmp_path/'bad').exists()
        with pytest.raises(ValueError):m.capture(state,auth,out)
