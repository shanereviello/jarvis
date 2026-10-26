"""Capture mutable Hermes proposals for operator review; approve one execution.

Operator CLI only. No worker launch or publication. Root-owned records are kept
separate from Hermes-writable proposals and worker-writable execution state.
"""
import argparse
from contextlib import contextmanager
import fcntl
import stat
import importlib.util
import json
import os
from pathlib import Path
import re
import uuid


def local(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def exact_digest(value):
    if not isinstance(value,str) or not re.fullmatch('[0-9a-f]{64}',value):raise ValueError('exact digest required')
    return value


def capture(proposals,submission_id,policy,registry,state,profile,codex_config,*,baseline_ref=None,expected_baseline=None,review_branch=None):
    a=local('activity');contract=local('task_contract');submission_id=exact_digest(submission_id)
    receipt=a.load(Path(proposals)/(submission_id+'.json'))
    if a.digest(a.encoded(receipt))!=submission_id:raise ValueError('proposal digest mismatch')
    fields={'schema_version','authenticated_identity','policy_sha256','request','execution_authorized','publication_authorized'}
    if set(receipt)!=fields or receipt['schema_version']!=1 or receipt['authenticated_identity']!='hermes':raise ValueError('unexpected proposal identity/schema')
    if receipt['execution_authorized'] is not False or receipt['publication_authorized'] is not False:raise ValueError('proposal cannot grant authority')
    raw_policy=Path(policy).read_bytes();current=json.loads(raw_policy)
    if receipt['policy_sha256']!=a.digest(raw_policy):raise ValueError('policy changed; prepare a new proposal')
    request=contract.validate_request(receipt['request'])
    if request['task_id'].startswith('TASK-preparation-acceptance-'):raise ValueError('installation acceptance proposals cannot execute')
    repo_id=request['repository_id'];row=current['repositories'][repo_id]
    if repo_id not in current['identities'].get('hermes',[]) or row['enabled'] is not True:raise ValueError('admission revoked')
    if not set(request['allowed_paths'])<=set(row['allowed_paths']):raise ValueError('paths not admitted')
    if request['validation_argv'] not in row['validations'].values():raise ValueError('validation not admitted')
    for field in ('worker_timeout_seconds','validation_timeout_seconds'):
        if request[field]!=row[field]:raise ValueError('execution limits changed')
    registered=a.registration(registry,repo_id)
    return snapshot(request, registered['path'], registered['hermes_project'], state, profile, codex_config,
                    submission_id, receipt['policy_sha256'], baseline_ref=baseline_ref,
                    expected_baseline=expected_baseline, review_branch=review_branch)


def snapshot(request, repository, hermes_project, state, profile, codex_config,
             submission_id, policy_sha256, *, baseline_ref=None, expected_baseline=None,
             review_branch=None, admission=None):
    """Snapshot inputs already admitted by a trusted capture adapter; no approval.

    This shared constructor does not authenticate a proposal or register a repo.
    Callers must enforce their admission boundary before invoking it.
    """
    a=local('activity');local('task_contract').validate_request(request)
    exact_digest(submission_id);exact_digest(policy_sha256);a.identifier(hermes_project)
    repo=a.canonical_repo(repository)
    if a.git(repo,'status','--porcelain','--untracked-files=all').strip():raise ValueError('clean canonical baseline required')
    if (baseline_ref is None)!=(expected_baseline is None):raise ValueError('named baseline and exact commit required together')
    ref=baseline_ref or 'HEAD'
    if baseline_ref and not re.fullmatch(r'refs/(heads|remotes/origin)/[A-Za-z0-9][A-Za-z0-9_/-]{0,120}',ref):raise ValueError('explicit branch ref required')
    if expected_baseline and not re.fullmatch('[0-9a-f]{40}',expected_baseline):raise ValueError('exact baseline commit required')
    baseline=a.git(repo,'rev-parse','--verify','--end-of-options',ref+'^{commit}').decode().strip()
    if expected_baseline and baseline!=expected_baseline:raise ValueError('baseline ref moved; review again')
    if review_branch and not re.fullmatch(r'codex/[A-Za-z0-9][A-Za-z0-9_-]{0,120}',review_branch):raise ValueError('dedicated review branch required')
    review={'schema_version':1,'submission_id':submission_id,'policy_sha256':policy_sha256,
            'request':request,'canonical_repository':str(repo),
            'baseline_commit':baseline,'baseline_ref':ref,
            'hermes_project':hermes_project,
            'profile':str(Path(profile).resolve(strict=True)), 'profile_sha256':a.digest(Path(profile).read_bytes()),
            'codex_config':str(Path(codex_config).resolve(strict=True)), 'codex_config_sha256':a.digest(Path(codex_config).read_bytes()),
            'runner_files':{n:a.digest(Path(__file__).with_name(n).read_bytes()) for n in ('manual_runner.py','task_contract.py','activity.py','credentials.py','wait_worker.py','native_task_cli.py')},
            'execution_authorized':False,'publication_authorized':False}
    if review_branch:review['review_branch']=review_branch
    if admission is not None:review['admission']=admission
    review_id=a.digest(a.encoded(review));base=a.private_dir(state)
    a.absent(base/(review_id+'.review.json'),a.encoded(review))
    return {'review_id':review_id,'review':review}


def read_review(state,review_id):
    a=local('activity');review_id=exact_digest(review_id)
    review=a.load(Path(state)/(review_id+'.review.json'))
    if a.digest(a.encoded(review))!=review_id:raise ValueError('review changed')
    return review


@contextmanager
def protocol_lock(state):
    fd=os.open(Path(state)/'.approval-protocol.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        info=os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid!=os.geteuid() or info.st_nlink!=1 or
                stat.S_IMODE(info.st_mode)!=0o600):raise ValueError('private approval protocol lock required')
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('another approval operation is active') from None
        yield
    finally:os.close(fd)


def validate_authorization(state,approval):
    fields={'schema_version','authorization_id','review_id','execution_authorized','publication_authorized','authorized_os_uid'}
    if (type(approval.get('schema_version')) is not int or approval['schema_version'] not in (1,2) or
            approval.get('execution_authorized') is not True or approval.get('publication_authorized') is not False or
            type(approval.get('authorized_os_uid')) is not int or approval.get('authorized_os_uid')!=0):raise ValueError('invalid approval protocol')
    if approval['schema_version']==1:
        if set(approval)!=fields:raise ValueError('invalid legacy authorization fields')
    else:local('document_approval').verify_authorization(state,approval)


def approve(state,review_id):
    a=local('activity')
    with protocol_lock(state):
        review=read_review(state,review_id)
        marker=Path(state)/(review_id+'.review-document.json')
        if marker.exists() or marker.is_symlink():raise ValueError('document-bound approval required for this capture')
        authorization_id=uuid.uuid4().hex
        approval={'schema_version':1,'authorization_id':authorization_id,'review_id':review_id,
                  'execution_authorized':True,'publication_authorized':False,
                  'authorized_os_uid':os.getuid()}
        a.absent(Path(state)/(authorization_id+'.approval.json'),a.encoded(approval))
    return approval


def consume(state,authorization_id):
    # Must happen before contacting the service manager; ambiguous launch cannot retry.
    if not re.fullmatch('[0-9a-f]{32}',authorization_id):raise ValueError('exact authorization ID required')
    a=local('activity');root=Path(state);approval=a.load(root/(authorization_id+'.approval.json'))
    if approval['authorization_id']!=authorization_id or approval['execution_authorized'] is not True or approval['publication_authorized'] is not False or approval['authorized_os_uid']!=0:raise ValueError('invalid approval')
    validate_authorization(state,approval)
    review=read_review(root,approval['review_id'])
    # Unlike evidence's idempotent writes, consumption is deliberately exclusive.
    with (root/(authorization_id+'.consumed.json')).open('xb') as stream:
        os.fchmod(stream.fileno(),0o600)
        stream.write(a.encoded({'authorization_id':authorization_id,'review_id':approval['review_id'],'launch_outcome':'not_yet_established'}))
        stream.flush();os.fsync(stream.fileno())
    a.fsync_directory(root)
    return review


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--action',choices=('capture','approve'),required=True)
    parser.add_argument('--state',type=Path,required=True)
    parser.add_argument('--proposals',type=Path);parser.add_argument('--submission-id')
    parser.add_argument('--policy',type=Path);parser.add_argument('--registry',type=Path)
    parser.add_argument('--profile',type=Path);parser.add_argument('--codex-config',type=Path)
    parser.add_argument('--baseline-ref');parser.add_argument('--expected-baseline');parser.add_argument('--review-branch')
    parser.add_argument('--review-id');parser.add_argument('--approve-one-execution',action='store_true')
    args=parser.parse_args()
    if os.geteuid()!=0:parser.error('operator administrator invocation required')
    # Root-private authority; a Hermes/worker-writable ancestor is not acceptable.
    for parent in args.state.absolute().parents:
        info=parent.stat()
        if parent.is_symlink() or info.st_uid!=0 or info.st_mode&0o022:parser.error('root-protected approval ancestors required')
    if args.action=='capture':
        if not all((args.proposals,args.submission_id,args.policy,args.registry,args.profile,args.codex_config)):parser.error('proposal, policy and registry required')
        result=capture(args.proposals,args.submission_id,args.policy,args.registry,args.state,args.profile,args.codex_config,baseline_ref=args.baseline_ref,expected_baseline=args.expected_baseline,review_branch=args.review_branch)
    else:
        info=args.state.stat()
        if args.state.is_symlink() or not args.state.is_dir() or info.st_uid!=0 or info.st_mode&0o077:parser.error('root-private approval state required')
        if not args.review_id or not args.approve_one_execution:parser.error('exact review digest and explicit one-execution approval required')
        result=approve(args.state,args.review_id)
    print(json.dumps(result))
