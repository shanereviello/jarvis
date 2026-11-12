"""Build an execution-policy candidate from independently verified pins.

This does not write a policy, provision a workspace, change a service, or
authorize spending. The verifier belongs to a protected operator-side process
and must query retained history and actual Linear identities independently.
"""
import copy
import importlib.util
from pathlib import Path
import re


def local(name):
    spec=importlib.util.spec_from_file_location('onboarding_admission_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def candidate(current,request,verify,verify_authority):
    runtime=local('codex_runtime');d=local('onboarding_drafts')
    policy=runtime.policy(current)
    if policy['contract']!='codex-runtime-policy.v2' or not callable(verify) or not callable(verify_authority):
        raise ValueError('protected isolated-workspace policy required')
    fields={'issue_id','organization_id','linear_project_id','team_id','scope','project_id','work_id','plan_id',
            'work_revision_sha256','assignment_sha256','architecture_version','architecture_sha256',
            'decision_receipt_sha256','workspace','native_socket','baseline_commit'}
    if type(request) is not dict or set(request)!=fields:raise ValueError('exact execution admission required')
    value=copy.deepcopy(request)
    for key in ('issue_id','organization_id','linear_project_id','team_id'):d.identifier(value[key])
    scope=d.selected_scope(value['scope'])
    if scope['kind']!='repository':raise ValueError('explicit repository required for coding')
    if value['organization_id']!=policy['organization_id']:raise ValueError('workspace organization differs')
    plan=value['plan_id']
    if type(plan) is not str or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,95}',plan):raise ValueError('exact plan required')
    if (value['project_id']!=d.identity('prj_',value['organization_id'],value['linear_project_id']) or
            value['work_id']!=d.work_identity('wrk_',value['organization_id'],value['linear_project_id'],plan)):
        raise ValueError('project or work identity differs')
    for key in ('work_revision_sha256','assignment_sha256','architecture_sha256','decision_receipt_sha256'):
        if type(value[key]) is not str or not re.fullmatch('[0-9a-f]{64}',value[key]):raise ValueError('exact evidence digest required')
    if type(value['architecture_version']) is not int or value['architecture_version']<1:
        raise ValueError('exact governing version required')
    if type(value['baseline_commit']) is not str or not re.fullmatch('[0-9a-f]{40}|[0-9a-f]{64}',value['baseline_commit']):
        raise ValueError('exact repository baseline required')
    if value['issue_id'] in policy['issues']:raise ValueError('issue already admitted; reconcile explicitly')
    # The verifier must compare the independently read issue, approved
    # decision, governing document bytes, current work and assignment receipts,
    # and checked-out repository baseline with this exact candidate.
    if verify(copy.deepcopy(value)) is not True:raise ValueError('execution evidence not verified')
    # Existing global runtime authority may cover only prior issues. An
    # approved architecture or a previously enabled runtime does not itself
    # authorize paid execution for this new issue.
    if verify_authority(copy.deepcopy(value)) is not True:raise ValueError('issue execution authority not verified')
    pin={key:value[key] for key in ('project_id','work_id','plan_id','work_revision_sha256','architecture_version','architecture_sha256')}
    policy['issues'][value['issue_id']]=pin
    policy['workspaces'][value['issue_id']]=value['workspace']
    policy['native_sockets'][value['issue_id']]=value['native_socket']
    result=runtime.policy(policy)
    return dict(policy=result,decision_receipt_sha256=value['decision_receipt_sha256'],
                assignment_sha256=value['assignment_sha256'],baseline_commit=value['baseline_commit'],
                policy_installed=False,execution_authority_changed=False)
