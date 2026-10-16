"""Human-readable review from the protected handoff manifest, no remote writes."""
import re


def render(record):
    p=record['prepared']
    if type(p['validation_exit']) is not int or p['validation_exit']!=0 or p['worker_stop_verified'] is not True or p['host_stop_verified'] is not True:
        raise ValueError('successful verified review evidence required')
    if p['merge_authorized'] is not False or p['deploy_authorized'] is not False:raise ValueError('separate human decisions required')
    for field in ('task_id','native_task'):
        if not re.fullmatch('[A-Za-z0-9_-]{1,160}',p[field]):raise ValueError('invalid review identity')
    if not re.fullmatch('[0-9a-f]{40}',p['commit']) or not re.fullmatch('[0-9a-f]{40}',p['baseline']):raise ValueError('exact commits required')
    if not re.fullmatch('[0-9a-f]{64}',p['export_id']):raise ValueError('exact export required')
    if not re.fullmatch('codex/[A-Za-z0-9][A-Za-z0-9_-]{0,120}',p['branch']):raise ValueError('review branch required')
    if type(p['native_run']) is not int or p['native_run']<1:raise ValueError('native run identity required')
    if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_/-]{0,120}',p['pr_base_branch']):raise ValueError('invalid PR base branch')
    remote=re.fullmatch(r'git@github\.com:([A-Za-z0-9_-]+/[A-Za-z0-9_.-]+)\.git',p['remote'])
    comparison=('https://github.com/'+remote[1]+'/compare/'+p['baseline']+'...'+p['commit']) if remote else 'Local fixture; no GitHub comparison.'
    return '\n'.join([
        '# Task review: '+p['task_id'], '',
        'Branch: `'+p['branch']+'`',
        'PR base branch: `'+p['pr_base_branch']+'`',
        'Baseline: `'+p['baseline']+'`',
        'Review commit: `'+p['commit']+'`',
        'Native task/run: `'+p['native_task']+'` / `'+str(p['native_run'])+'`',
        'Evidence export: `'+p['export_id']+'`', '',
        'Independent validation: passed (exit 0). Worker and host stop: verified.',
        'Scope: checked against the admitted task before commit preparation.', '',
        comparison, '',
        'Publication status is recorded separately in publication-receipt.json; this summary does not prove a push.',
        'Human review: inspect the complete diff and retained validation evidence.',
        'Merge: awaiting separate human decision.',
        'Deployment and robot hardware/field validation: awaiting separate human decision.', '',
    ])
