"""Construct an additive planning/operator policy candidate; never install it."""
import copy
import importlib.util
from pathlib import Path


def local(name):
    path=Path(__file__).resolve().parent.parent/'rras_history'/(name+'.py')
    spec=importlib.util.spec_from_file_location('onboarding_policy_'+name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def candidate(existing,organization_id,team_id,jarvis_uid,codex_uid,operator_uid):
    if (type(existing) is not dict or set(existing)!={'contract','principals'} or
            existing['contract']!='engineering-history-access.v2'):
        raise ValueError('exact existing v2 policy required')
    local('onboarding_reservations').canonical(organization_id);local('onboarding_reservations').canonical(team_id)
    ids=(jarvis_uid,codex_uid,operator_uid)
    if any(type(x) is not int or not 1<=x<2**32-1 for x in ids) or len(set(ids))!=3:
        raise ValueError('three distinct dedicated identities required')
    local('access').Access(None,existing)
    if any(p['uid'] in ids for p in existing['principals']):raise ValueError('new identity collides with existing principal')
    upgraded=[]
    for principal in existing['principals']:
        upgraded.append(dict(copy.deepcopy(principal),planning_agent=None,planning_organization_id=None,
                             planning_teams=[],planning_repositories=[],planning_categories=[]))
    for agent,uid in (('jarvis',jarvis_uid),('codex',codex_uid)):
        upgraded.append(dict(uid=uid,private_read=['jarvis'],write=[],category_read=['jarvis-non-git'],category_write=[],
            planning_agent=agent,planning_organization_id=organization_id,planning_teams=[team_id],
            planning_repositories=['jarvis'],planning_categories=['jarvis-non-git']))
    upgraded.append(dict(uid=operator_uid,private_read=['jarvis'],write=['jarvis'],category_read=['jarvis-non-git'],
        category_write=['jarvis-non-git'],planning_agent=None,planning_organization_id=None,planning_teams=[],
        planning_repositories=[],planning_categories=[]))
    result=dict(contract='engineering-history-access.v3',principals=upgraded)
    local('access').Access(None,result)
    return result
