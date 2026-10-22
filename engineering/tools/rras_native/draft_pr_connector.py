"""Named-operator intent/fence/receipt bridge for the existing GitHub connector.

No token, HTTP client, worker launch, push, merge/deploy or creation retry here.
The operator frontend supplies the authenticated connector; files retain provenance.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
from urllib.parse import quote


def local(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(name+'.py'))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def context(package,workspace):
    local('approved_launch').trusted(Path(__file__))
    record,_=local('publication_handoff').read(package)
    workspace=local('publication_handoff').workspace_path(record,workspace);s=workspace.lstat()
    if (not workspace.is_absolute() or workspace.resolve(strict=True)!=workspace or s.st_uid!=os.getuid() or
            stat.S_IMODE(s.st_mode)!=0o700 or os.getuid() in (0,996,997)):
        raise ValueError('named operator private workspace required')
    p=record['prepared'];a=local('activity');read=local('workflow_publication').operator_bytes
    report=local('workflow_journal').decode(read(workspace/'publication-receipt.json',record['operator_uid']))
    started=local('workflow_journal').decode(read(workspace/'publication-receipt.json.started',record['operator_uid']))
    if not local('workflow_publication').transport_report(p,report,started):raise ValueError('verified published branch report required')
    local('publication_policy').plan(record['policy'],p['repository_id'],p['branch'],p['branch'],action='draft_pr',
        worker_stop_verified=p['worker_stop_verified'],host_stop_verified=p['host_stop_verified'],
        validation_exit=p['validation_exit'],scope_verified=True,task_success=True)
    prepared=dict(p,checkout=str(workspace/'repo'))
    local('publication_transport').verify(prepared,record['policy'])
    match=re.fullmatch(r'git@github\.com:([A-Za-z0-9_-]+/[A-Za-z0-9_.-]+)\.git',p['remote'])
    if not match:raise ValueError('supported GitHub remote required')
    repository=match[1];owner=repository.split('/')[0]
    body=('Task: '+p['task_id']+'\n\nReview commit: '+p['commit']+'\nBaseline: '+p['baseline']+
          '\nEvidence export: '+p['export_id']+'\n\nCaptured runner validation reports exit 0; runner-result provenance remains imported. '+
          'Scope and commit were checked by the trusted publication adapter. Human deliverable review, merge and deployment remain separate.')
    if record.get('independent_validation_required') is True:
        body += '\nThe protected publisher also verified an independent host mechanical-validation receipt for this exact review commit.'
    create={'repository_full_name':repository,'head':p['branch'],'base':p['pr_base_branch'],
            'draft':True,'maintainer_can_modify':False,'title':p['task_id']+': reviewed task changes','body':body}
    identity={'schema_version':1,'operator_uid':record['operator_uid'],'handoff_sha256':a.digest(a.encoded(record)),
        'publication_receipt_sha256':a.digest(a.encoded(report)),'commit':p['commit'],'create':create,
        'branch_read':{'url':'https://api.github.com/repos/'+repository+'/branches/'+quote(p['branch'],safe='/')},
        'prs_read':{'url':'https://api.github.com/repos/'+repository+'/pulls?state=all&head='+quote(owner+':'+p['branch'],safe='')+'&per_page=1'}}
    return workspace,p,identity


def exclusive(path,value):
    a=local('activity');raw=a.encoded(value)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    a.fsync_directory(path.parent)


def absent_outcome(workspace):
    for name in ('draft-pr-outcome.json','draft-pr-receipt.json'):
        p=workspace/name
        if p.exists() or p.is_symlink():raise ValueError('draft PR outcome already exists; inspect without retry')


def prepare(package,workspace):
    workspace,p,intent=context(package,workspace);a=local('activity');absent_outcome(workspace)
    if (workspace/'draft-pr-armed.json').exists() or (workspace/'draft-pr-armed.json').is_symlink():
        raise ValueError('draft PR creation already armed; inspect without retry')
    a.absent(workspace/'draft-pr-intent.json',a.encoded(intent))
    return dict(intent,intent_sha256=a.digest(a.encoded(intent)))


def saved_context(package,workspace):
    workspace,p,intent=context(package,workspace);a=local('activity')
    raw=local('workflow_publication').operator_bytes(workspace/'draft-pr-intent.json',os.getuid())
    if raw!=a.encoded(intent):raise ValueError('draft PR intent/package changed')
    return workspace,p,intent,a.digest(raw)


def arm(package,workspace,data):
    workspace,p,intent,sha=saved_context(package,workspace);absent_outcome(workspace)
    if (set(data)!={'branch','prs'} or not isinstance(data['branch'],dict) or not isinstance(data['prs'],list) or data['prs'] or
            data['branch'].get('name')!=p['branch'] or not isinstance(data['branch'].get('commit'),dict) or
            data['branch']['commit'].get('sha')!=p['commit']):
        raise ValueError('live branch differs or PR already exists')
    exclusive(workspace/'draft-pr-armed.json',{'schema_version':1,'intent_sha256':sha,'creation_may_have_occurred':True})
    return {'armed':True,'intent_sha256':sha,'create':intent['create']}


def armed_context(package,workspace):
    workspace,p,intent,sha=saved_context(package,workspace);absent_outcome(workspace)
    raw=local('workflow_publication').operator_bytes(workspace/'draft-pr-armed.json',os.getuid())
    if local('workflow_journal').decode(raw)!={'schema_version':1,'intent_sha256':sha,'creation_may_have_occurred':True}:
        raise ValueError('draft PR fence changed')
    return workspace,p,intent,sha


def normalize(prepared,snapshot):
    # Connector normalized snapshot and GitHub REST response are explicit shapes.
    if isinstance(snapshot.get('head'),dict):
        head=snapshot['head'];base=snapshot['base']
        branch,commit,repo=head['ref'],head['sha'],head['repo']['full_name'];base_ref=base['ref'];url=snapshot['html_url']
    else:
        branch,commit,repo=snapshot['head'],snapshot['head_sha'],snapshot['head_repo_full_name'];base_ref=snapshot['base'];url=snapshot['url']
    remote=re.fullmatch(r'git@github\.com:([A-Za-z0-9_-]+/[A-Za-z0-9_.-]+)\.git',prepared['remote'])
    report={'schema_version':1,'repository':remote[1],'head_repository':repo,'head_branch':branch,'head_commit':commit,
        'base_branch':base_ref,'number':snapshot['number'],'url':url,'draft':snapshot['draft'],
        'merged':snapshot['merged'],'state':snapshot['state']}
    return local('workflow_publication').pr_report(prepared,report)


def unknown(package,workspace,candidate=None):
    workspace,p,intent,sha=armed_context(package,workspace)
    result={'schema_version':1,'intent_sha256':sha,'status':'unknown','automatic_retry':False,
            'merge_authorized':False,'deploy_authorized':False}
    if candidate:result['candidate_for_inspection']=candidate
    exclusive(workspace/'draft-pr-outcome.json',result)
    return result


def complete(package,workspace,data):
    workspace,p,intent,sha=armed_context(package,workspace)
    try:report=normalize(p,data)
    except (ValueError,KeyError,TypeError):
        candidate=None
        number=data.get('number');url=data.get('html_url',data.get('url'))
        repository=intent['create']['repository_full_name']
        if type(number) is int and number>0 and url=='https://github.com/'+repository+'/pull/'+str(number):
            candidate={'number':number,'url':url}
        return unknown(package,workspace,candidate)
    exclusive(workspace/'draft-pr-receipt.json',report)
    result={'schema_version':1,'intent_sha256':sha,'status':'draft_created','url':report['url'],'number':report['number'],
            'receipt_sha256':local('activity').digest(local('activity').encoded(report)),
            'automatic_retry':False,'merge_authorized':False,'deploy_authorized':False}
    exclusive(workspace/'draft-pr-outcome.json',result)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('prepare','arm','complete','unknown'))
    p.add_argument('--package',required=True);p.add_argument('--workspace');p.add_argument('--data')
    args=p.parse_args()
    try:
        if args.action in ('prepare','unknown'):answer=globals()[args.action](args.package,args.workspace)
        else:
            if args.data is None or len(args.data.encode())>1024*1024:raise ValueError('bounded connector metadata required')
            data=local('workflow_journal').decode(args.data.encode())
            if not isinstance(data,dict):raise ValueError('connector object required')
            answer=globals()[args.action](args.package,args.workspace,data)
        print(json.dumps(dict(answer,operator_binding_protocol=1)))
    except (ValueError,OSError,KeyError,TypeError):p.exit(1,'Draft PR bridge refused; preserve intent/fence and inspect without creation retry.\n')


if __name__=='__main__':main()
