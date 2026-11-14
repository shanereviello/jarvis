"""Classify an interrupted issue-policy cutover without changing state.

A protected operator must inspect this result under the admission lock, with
runtime stopped and with an independently authenticated transition plan. This
module never starts or stops services, changes files, or retries execution.
"""
import re


def classify(*,old_policy_sha256,new_policy_sha256,journal_policy_sha256,file_policy_sha256,runtime_stopped):
    values=(old_policy_sha256,new_policy_sha256,journal_policy_sha256,file_policy_sha256)
    if any(type(x) is not str or not re.fullmatch('[0-9a-f]{64}',x) for x in values) or old_policy_sha256==new_policy_sha256:
        raise ValueError('four exact policy digests and a distinct transition required')
    if runtime_stopped is not True:raise ValueError('runtime must be stopped before inspecting cutover')
    old,new=old_policy_sha256,new_policy_sha256
    states={(old,old):'not_started',(new,new):'consistent_new',(new,old):'journal_ahead',(old,new):'file_ahead'}
    return dict(state=states.get((journal_policy_sha256,file_policy_sha256),'conflict'),
                automatic_change=False,automatic_retry=False,execution_authorized_changed=False)
