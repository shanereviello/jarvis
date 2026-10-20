"""Bind named-operator publication reports to protected finish custody and journal.

No remote contact, credential access, worker/service mutation or publication retry.
Captured operator/API reports retain imported provenance, never release authority.
"""
import importlib.util
import os
from pathlib import Path
import re
import stat


def local(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def decode(raw):return local('workflow_journal').decode(raw)


def operator_bytes(path,uid,limit=1024*1024):
    path=Path(path)
    if type(uid) is not int or uid in (0,996,997) or not path.is_absolute() or path.resolve(strict=True)!=path:
        raise ValueError('named operator non-symlink source required')
    for parent in path.parents:
        s=parent.lstat()
        if not stat.S_ISDIR(s.st_mode) or s.st_uid not in (0,uid) or s.st_mode&0o022:
            raise ValueError('operator source ancestor is writable or unowned')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        s=os.fstat(fd)
        if not stat.S_ISREG(s.st_mode) or s.st_uid!=uid or s.st_mode&0o077 or s.st_nlink!=1 or s.st_size>limit:
            raise ValueError('private bounded operator receipt required')
        with os.fdopen(os.dup(fd),'rb') as f:raw=f.read(limit+1)
        if len(raw)>limit:raise ValueError('operator receipt exceeds bound')
        return raw
    finally:os.close(fd)


def handoff(package,finish,review,members):
    custody=local('publication_custody');a=local('activity');root=Path(package)
    raw=custody.root_bytes(root/'handoff.json',1024*1024);record=decode(raw)
    if (record['schema_version']!=1 or type(record['operator_uid']) is not int or
            record['operator_uid'] in (0,996,997)):
        raise ValueError('named operator handoff required')
    data=custody.root_bytes(root/'review.bundle',local('publication_handoff').LIMIT)
    if len(data)!=record['bundle_size'] or a.digest(data)!=record['bundle_sha256']:
        raise ValueError('handoff bundle changed')
    validate_handoff(record,finish,review,members)
    return raw,record


def validate_handoff(record,finish,review,members):
    p=record['prepared'];evidence=decode(members['evidence.json'])
    if (finish['facts']['outcome']!='succeeded' or not finish['facts']['terminal'] or
            p['repository_id']!=review['request']['repository_id'] or p['task_id']!=review['request']['task_id'] or
            p['branch']!=review['review_branch'] or p['baseline']!=review['baseline_commit'] or
            p['export_id']!=evidence['export']['export_id'] or p['native_task']!=evidence['native_task'] or
            type(p['native_run']) is not int or p['native_run']!=evidence['native_run']):
        raise ValueError('finish/handoff task association mismatch')
    planner=local('publication_policy')
    plan=planner.plan(record['policy'],p['repository_id'],p['branch'],review['review_branch'],
        worker_stop_verified=p['worker_stop_verified'],host_stop_verified=p['host_stop_verified'],
        validation_exit=p['validation_exit'],scope_verified=True,task_success=True)
    if any(p.get(k)!=v for k,v in plan.items()) or p['remote']!=review['admission']['registration']['publication']['remote']:
        raise ValueError('handoff policy/registration mismatch')
    if not re.fullmatch('[0-9a-f]{40}',p['commit']) or not isinstance(p['pr_base_branch'],str):
        raise ValueError('exact review commit/base required')
    if p['pr_base_branch']!=review['baseline_ref'].removeprefix('refs/heads/').removeprefix('refs/remotes/origin/'):
        raise ValueError('PR base differs from reviewed baseline')


def transport_report(prepared,report,started):
    identity={k:prepared[k] for k in ('repository_id','remote','branch','refspec','commit','baseline','export_id')}
    identity.update(schema_version=1,merge_authorized=False,deploy_authorized=False)
    if started!=identity or any(report.get(k)!=v or type(report.get(k)) is not type(v) for k,v in identity.items()):
        raise ValueError('publication receipt association mismatch')
    allowed=set(identity)|{'status','remote_write_attempted','error_type'}
    if (set(report)-allowed or report.get('status') not in ('published','unknown') or
            type(report.get('remote_write_attempted')) is not bool):
        raise ValueError('invalid publication receipt')
    if report['status']=='published' and (not report['remote_write_attempted'] or 'error_type' in report):
        raise ValueError('published report contradicts transport facts')
    return report['status']=='published'


def pr_report(prepared,report):
    fields={'schema_version','repository','head_repository','head_branch','head_commit','base_branch','number','url','draft','merged','state'}
    match=re.fullmatch(r'git@github\.com:([A-Za-z0-9_-]+/[A-Za-z0-9_.-]+)\.git',prepared['remote'])
    if not match or set(report)!=fields or type(report['schema_version']) is not int or report['schema_version']!=1:
        raise ValueError('normalized GitHub draft-PR receipt required')
    repo=match[1]
    if (report['repository']!=repo or report['head_repository']!=repo or report['head_branch']!=prepared['branch'] or
            report['head_commit']!=prepared['commit'] or report['base_branch']!=prepared['pr_base_branch'] or
            type(report['number']) is not int or report['number']<1 or
            report['url']!='https://github.com/'+repo+'/pull/'+str(report['number']) or
            report['draft'] is not True or report['merged'] is not False or report['state']!='open'):
        raise ValueError('draft PR differs from reviewed branch/commit/base')
    return report


def prepare(finish_custody,policy_path,destination,package,operator):
    """Prepare a local review commit and source-only operator bundle; no push."""
    finish,review,members=local('workflow_finish').load(finish_custody)
    if finish['facts']!={'outcome':'succeeded','terminal':True,'validation':'succeeded'}:
        raise ValueError('successful complete captured report required')
    a=local('activity');custody=local('publication_custody');launch=local('approved_launch')
    destination=Path(destination);package=Path(package)
    for path in (destination,package):
        if not path.is_absolute():raise ValueError('absolute publication destination required')
        launch.trusted(path.parent)
        if path.exists() or path.is_symlink():raise ValueError('fresh publication destination required')
    prepared_path=Path(str(destination)+'.prepared.json')
    if prepared_path.exists() or prepared_path.is_symlink():raise ValueError('prepared receipt exists')
    policy_raw=custody.root_bytes(policy_path,1024*1024);policy=decode(policy_raw)
    if policy['repositories'][review['request']['repository_id']]['remote']!=review['admission']['registration']['publication']['remote']:
        raise ValueError('policy differs from admitted publication remote')
    files={name.removeprefix('artifacts/'):data for name,data in members.items() if name.startswith('artifacts/')}
    result=local('publication').prepare(review['canonical_repository'],destination,policy,review['review_branch'],
        review,decode(members['host-result.json']),decode(members['evidence.json']),decode(members['manifest.json']),files)
    result['policy_sha256']=a.digest(policy_raw)
    a.absent(prepared_path,a.encoded(result))
    local('publication_handoff').export(prepared_path,policy_path,package,operator,validation_required=True)
    return {'prepared':True,'commit':result['commit'],'branch':result['branch'],'remote_contacted':False,
            'merge_authorized':False,'deploy_authorized':False}


def capture(finish_custody,package,workspace,destination,pr_receipt=None):
    finish,review,members=local('workflow_finish').load(finish_custody)
    a=local('activity');handoff_raw,record=handoff(package,finish,review,members)
    proof=local('publication_handoff').require_validation(record,package)
    uid=record['operator_uid'];workspace=Path(workspace);destination=Path(destination)
    if not destination.is_absolute():raise ValueError('absolute publication custody required')
    local('approved_launch').trusted(destination.parent)
    if destination.exists() or destination.is_symlink():raise ValueError('fresh publication custody required')
    s=workspace.lstat()
    if not workspace.is_absolute() or workspace.is_symlink() or s.st_uid!=uid or stat.S_IMODE(s.st_mode)!=0o700:
        raise ValueError('named operator private workspace required')
    raw=operator_bytes(workspace/'publication-receipt.json',uid)
    started_raw=operator_bytes(workspace/'publication-receipt.json.started',uid)
    report,started=decode(raw),decode(started_raw)
    published=transport_report(record['prepared'],report,started)
    captured={'handoff.json':handoff_raw,'transport.json':raw,'transport-started.json':started_raw}
    if proof is not None:captured['independent-validation.json']=a.encoded(proof)
    if pr_receipt is not None:
        if not published:raise ValueError('unknown branch transport cannot establish PR opening')
        pr_raw=operator_bytes(pr_receipt,uid);pr_report(record['prepared'],decode(pr_raw));captured['draft-pr.json']=pr_raw
    capture_record={'schema_version':1,'authorization_id':finish['authorization_id'],'review_id':finish['review_id'],
        'finish_capture_sha256':a.digest(a.encoded(finish)),
        'files':{k:a.digest(v) for k,v in captured.items()}}
    destination.mkdir(mode=0o700);a.fsync_directory(destination.parent)
    for name,raw in captured.items():a.absent(destination/name,raw)
    a.absent(destination/'publication-capture.json',a.encoded(capture_record))
    return {'captured':True,'reported_branch_status':report['status'],'draft_pr_captured':pr_receipt is not None,
            'remote_contacted':False,'merge_authorized':False,'deploy_authorized':False}


def load(finish_custody,custody):
    finish,review,finish_members=local('workflow_finish').load(finish_custody)
    root=Path(custody);read=local('publication_custody').root_bytes;a=local('activity')
    local('approved_launch').trusted(Path(__file__))
    if not root.is_absolute() or stat.S_IMODE(root.stat().st_mode)!=0o700:raise ValueError('private publication custody required')
    receipt=decode(read(root/'publication-capture.json',1024*1024))
    if (receipt.get('schema_version')!=1 or receipt['authorization_id']!=finish['authorization_id'] or
            receipt['review_id']!=finish['review_id'] or receipt['finish_capture_sha256']!=a.digest(a.encoded(finish)) or
            set(receipt['files']) not in tuple({'handoff.json','transport.json','transport-started.json'}|extra for extra in
                (set(),{'draft-pr.json'},{'independent-validation.json'},{'draft-pr.json','independent-validation.json'}))):
        raise ValueError('publication/finish custody mismatch')
    members={}
    for name,sha in receipt['files'].items():
        raw=read(root/name,1024*1024)
        if a.digest(raw)!=sha:raise ValueError('publication custody changed')
        members[name]=raw
    record=decode(members['handoff.json']);validate_handoff(record,finish,review,finish_members);p=record['prepared']
    if record.get('independent_validation_required') is True:
        local('publication_handoff').validate_proof(record,decode(members['independent-validation.json']))
    # These exact protected handoff bytes were checked with the bundle at capture.
    # Recording never re-reads the operator workspace or contacts a remote.
    published=transport_report(p,decode(members['transport.json']),decode(members['transport-started.json']))
    if 'draft-pr.json' in members:
        if not published:raise ValueError('PR report without a published branch')
        pr_report(p,decode(members['draft-pr.json']))
    return finish,review,receipt,members


def record(finish_custody,custody):
    finish,review,receipt,members=load(finish_custody,custody)
    local('workflow_finish').record(finish_custody)
    events=local('managed_events');store=events.journal(review);a=local('activity')
    auth=finish['authorization_id'];p=decode(members['handoff.json'])['prepared']
    report=decode(members['transport.json']);work=review['admission']['work_item']
    branch_facts={'schema_version':1,'finish_capture_sha256':receipt['finish_capture_sha256'],
        'handoff_sha256':receipt['files']['handoff.json'],'transport_sha256':receipt['files']['transport.json'],
        'transport_started_sha256':receipt['files']['transport-started.json'],'repository_id':p['repository_id'],
        'branch':p['branch'],'commit':p['commit'],'baseline':p['baseline'],'export_id':p['export_id'],
        'reported_status':report['status'],'merge_authorized':False,'deploy_authorized':False}
    if 'independent-validation.json' in members:
        branch_facts['independent_validation_sha256']=receipt['files']['independent-validation.json']
    phases=[('branch', 'branch.published' if report['status']=='published' else 'recovery.recorded',
             'succeeded' if report['status']=='published' else 'uncertain',branch_facts)]
    if 'draft-pr.json' in members:
        pr=decode(members['draft-pr.json'])
        phases.append(('draft-pr','pull_request.opened','succeeded',dict(branch_facts,
            pr_receipt_sha256=receipt['files']['draft-pr.json'],number=pr['number'],url=pr['url'],draft=True)))
    for phase,kind,outcome,facts in phases:
        raw=a.encoded(facts);sha=a.digest(raw);actor={'type':'service','id':'workflow-publication'}
        event={'event_id':events.stable('evt_',auth,'publication',phase),'work_item_id':work['work_item_id'],
            'work_item_sha256':review['admission']['work_item_sha256'],'attempt_id':events.stable('att_',auth),
            'actor':actor,'provenance':{'kind':'imported','source':{'namespace':'external','id':'publication-report:'+sha},'source_sha256':sha,'recorded_by':actor},
            'event_type':kind,'outcome':outcome,
            'summary':'Captured named-operator publication report; remote state, human merge and deployment remain separately evidenced.',
            'artifacts':[{'artifact_id':events.stable('art_',auth,'publication',phase),'sha256':sha,'media_type':'application/json','visibility':'operator_only','purpose':'publication'}],
            'references':[{'namespace':'authorization','id':auth},{'namespace':'git_commit','id':p['commit']}],
            'corrects_event_id':None,'decision_subject':None}
        if phase=='draft-pr':event['references'].append({'namespace':'pull_request','id':facts['url']})
        store.append([],{sha:raw},transition=(event,None))
    return {'recorded':True,'reported_branch_status':report['status'],'draft_pr_recorded':'draft-pr.json' in members,
            'provenance':'imported','remote_contacted':False,'execution_retried':False,'merge_authorized':False,'deploy_authorized':False}
