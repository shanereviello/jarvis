"""Match one protected, explicitly scoped execution authority grant.

The caller must load this configuration from a root-controlled source. A
project-wide grant covers only independently verified mapped issues for the
exact approved architecture and repository; it is not an architecture decision.
This verifier does not install policy, run a model, or authenticate the human
who originally granted authority.
"""
from datetime import datetime,timezone
import hashlib
import json
import re
import importlib.util
from pathlib import Path


def canonical(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf-8')


def protected(path):
    spec=importlib.util.spec_from_file_location('execution_authority_protected',Path(__file__).with_name('protected_config.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return Verifier(module.decode(path,require_root=True))


class Verifier:
    def __init__(self,policy,clock=lambda:datetime.now(timezone.utc)):
        if type(policy) is not dict or set(policy)!={'contract','grants'} or policy['contract']!='codex-execution-grants.v1':
            raise ValueError('exact protected execution grants required')
        if type(policy['grants']) is not list or not 1<=len(policy['grants'])<=256 or not callable(clock):
            raise ValueError('bounded execution grants required')
        self.policy=json.loads(canonical(policy));self.sha=hashlib.sha256(canonical(policy)).hexdigest();self.clock=clock
        ids=set()
        for grant in self.policy['grants']:
            fields={'grant_id','organization_id','linear_project_id','project_id','repository_id','architecture_version',
                    'architecture_sha256','issue_ids','authorization_reference','expires_at'}
            if type(grant) is not dict or set(grant)!=fields:raise ValueError('exact execution grant required')
            if (type(grant['grant_id']) is not str or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,95}',grant['grant_id']) or
                    grant['grant_id'] in ids):raise ValueError('distinct grant identity required')
            ids.add(grant['grant_id'])
            for key in ('organization_id','linear_project_id'):
                if type(grant[key]) is not str or not re.fullmatch('[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',grant[key]):raise ValueError('exact grant identity required')
            if (type(grant['project_id']) is not str or not re.fullmatch('prj_[0-9a-f]{32}',grant['project_id']) or
                    type(grant['repository_id']) is not str or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,127}',grant['repository_id']) or
                    type(grant['architecture_version']) is not int or grant['architecture_version']<1 or
                    type(grant['architecture_sha256']) is not str or not re.fullmatch('[0-9a-f]{64}',grant['architecture_sha256'])):
                raise ValueError('exact project and architecture grant required')
            issues=grant['issue_ids']
            if issues is not None:
                if type(issues) is not list or not 1<=len(issues)<=256 or len(set(issues))!=len(issues):raise ValueError('bounded issue grant required')
                if any(type(x) is not str or not re.fullmatch('[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',x) for x in issues):raise ValueError('exact issue grant required')
            if type(grant['authorization_reference']) is not str or not 1<=len(grant['authorization_reference'].strip())<=512:
                raise ValueError('explicit execution authority source required')
            if grant['expires_at'] is not None:self.parse_time(grant['expires_at'])

    @staticmethod
    def parse_time(value):
        if type(value) is not str or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z',value):raise ValueError('exact UTC expiry required')
        return datetime.strptime(value,'%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)

    def __call__(self,value):
        now=self.clock()
        if not isinstance(now,datetime) or now.tzinfo is None:raise ValueError('trusted UTC clock required')
        matches=[]
        for g in self.policy['grants']:
            if (g['organization_id']==value['organization_id'] and g['linear_project_id']==value['linear_project_id'] and
                g['project_id']==value['project_id'] and value['scope']=={'kind':'repository','id':g['repository_id']} and
                g['architecture_version']==value['architecture_version'] and g['architecture_sha256']==value['architecture_sha256'] and
                (g['issue_ids'] is None or value['issue_id'] in g['issue_ids']) and
                (g['expires_at'] is None or now<self.parse_time(g['expires_at']))):matches.append(g)
        if len(matches)!=1:return False
        return dict(authorized=True,grant_id=matches[0]['grant_id'],reference=matches[0]['authorization_reference'],policy_sha256=self.sha)
