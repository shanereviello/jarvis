import copy
import importlib.util
from pathlib import Path

import pytest
from test_reporting_onboarding_drafts import uid


path=Path(__file__).resolve().parents[1]/'tools/rras_reporting/onboarding_access_policy_stage.py'
spec=importlib.util.spec_from_file_location('policy_stage_test',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def existing():
    return dict(contract='engineering-history-access.v2',principals=[
        dict(uid=1000,private_read=['jarvis','robot_ws'],write=['jarvis','robot_ws'],category_read=['jarvis-non-git'],category_write=['jarvis-non-git']),
        dict(uid=993,private_read=['jarvis'],write=[],category_read=['jarvis-non-git'],category_write=[])])


def test_additive_candidate_preserves_existing_and_scopes_new_roles():
    value=existing();before=copy.deepcopy(value)
    result=module.candidate(value,uid(1),uid(2),61180,61181,61182)
    assert value==before and result['contract']=='engineering-history-access.v3'
    for old,new in zip(before['principals'],result['principals']):
        assert all(new[key]==item for key,item in old.items()) and new['planning_agent'] is None
    jarvis,codex,operator=result['principals'][-3:]
    assert (jarvis['planning_agent'],codex['planning_agent'])==('jarvis','codex')
    assert jarvis['write']==codex['write']==[] and jarvis['category_write']==codex['category_write']==[]
    assert operator['write']==['jarvis'] and operator['category_write']==['jarvis-non-git']


@pytest.mark.parametrize('ids',[(1000,61181,61182),(61180,61180,61182),(61180,61181,0)])
def test_existing_or_invalid_identities_are_refused(ids):
    with pytest.raises(ValueError):module.candidate(existing(),uid(1),uid(2),*ids)
