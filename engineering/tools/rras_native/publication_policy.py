"""Standing review-branch publication policy; no credentials or remote writes.

Trusted publication caller supplies assigned branch and verified evidence. Model
arguments/proposals are not authority. This module never authorizes merge/deploy.
"""
import re


def plan(policy,repository_id,branch,assigned_branch,*,action='push',force=False,delete=False,
         worker_stop_verified=False,host_stop_verified=False,validation_exit=None,
         scope_verified=False,task_success=False):
    if policy.get('schema_version')!=1 or policy.get('review_branch_publication')!='standing-authorized':
        raise ValueError('standing publication not configured')
    if action not in ('push','draft_pr') or force or delete:raise ValueError('action requires human approval or is forbidden')
    if repository_id not in policy['repositories']:raise ValueError('repository not admitted')
    row=policy['repositories'][repository_id]
    # Deliberately narrow branch syntax; cannot encode refspecs, tags or deletion.
    if not isinstance(branch,str) or not re.fullmatch(r'codex/[A-Za-z0-9][A-Za-z0-9_-]{0,120}',branch):raise ValueError('dedicated review branch required')
    if branch!=assigned_branch or branch==row['default_branch'] or not branch.startswith(policy['branch_prefix']):raise ValueError('branch not assigned to task')
    if not all(x is True for x in (worker_stop_verified,host_stop_verified,scope_verified,task_success)) or type(validation_exit) is not int or validation_exit!=0:
        raise ValueError('verified successful task evidence required')
    return {'repository_id':repository_id,'remote':row['remote'],'branch':branch,
            'refspec':'HEAD:refs/heads/'+branch,'action':action,'force':False,
            'human_publication_confirmation_required':False,'merge_authorized':False,'deploy_authorized':False}
