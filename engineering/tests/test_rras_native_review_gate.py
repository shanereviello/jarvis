import importlib.util
from pathlib import Path
import pytest
from test_rras_native_publication import fixture
ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('review',ROOT/'tools/rras_native/review_gate.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

def test_review_links_exact_diff_and_keeps_merge_separate(fixture):
    spec=importlib.util.spec_from_file_location('publication',ROOT/'tools/rras_native/publication.py');pub=importlib.util.module_from_spec(spec);spec.loader.exec_module(pub)
    p=pub.prepare(**fixture);text=m.render({'prepared':p})
    assert p['baseline']+'...'+p['commit'] in text
    assert 'Merge: awaiting separate human decision.' in text
    assert 'does not prove a push' in text
    assert 'fixture' in text
    assert 'Mechanical validation does not establish deliverable completeness' in text
    assert 'Human review: pending.' in text

@pytest.mark.parametrize('field,value',[('worker_stop_verified',False),('merge_authorized',True),('task_id','bad\ntext')])
def test_bad_review_refused(field,value):
    p=dict(validation_exit=0,worker_stop_verified=True,host_stop_verified=True,merge_authorized=False,deploy_authorized=False,task_id='TASK-one',native_task='t_one')
    p[field]=value
    with pytest.raises(ValueError):m.render({'prepared':p})
