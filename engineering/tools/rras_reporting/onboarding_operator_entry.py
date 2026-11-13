"""Initialize or run the separately protected operator service; never deploy."""
import argparse
from contextlib import contextmanager, ExitStack
import fcntl
import importlib.util
import os
from pathlib import Path
import signal
import sqlite3
import stat
import threading


def local(name):
    spec=importlib.util.spec_from_file_location('operator_entry_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def web(name):
    path=Path(__file__).resolve().parent.parent/'rras_history_web'/(name+'.py')
    spec=importlib.util.spec_from_file_location('operator_web_'+name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def initialize(root):
    private=local('codex_runtime').private;root=Path(root)
    if not root.is_absolute() or root.resolve()!=root or root.exists():raise ValueError('new private operator state required')
    root.mkdir(mode=0o700,parents=False,exist_ok=False);private(root,True)
    path=root/'operator.sqlite3';fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600);os.close(fd)
    with sqlite3.connect(path) as db:local('onboarding_operator_service').initialize_empty(db)
    return dict(initialized=True,listener_started=False,execution_authorized=False)


def configuration(value,uid,gid):
    fields={'operator_uid','operator_gid','planning_peer_uid','browser_peer_uid','history_uid','history_socket',
            'review_socket','browser_socket','organization_id','app_user_id','team_id','human_ids','scopes',
            'reader_origin_url','reader_issue_url','comment_url','access'}
    if type(value) is not dict or not fields<=set(value) or set(value)-fields-{'admission','jarvis_review'}:raise ValueError('exact operator service configuration required')
    u=local('onboarding_broker_unix').unix()
    for name in ('operator_uid','operator_gid','planning_peer_uid','browser_peer_uid','history_uid'):u.uid(value[name])
    if (value['operator_uid']!=uid or value['operator_gid']!=gid or
            len({uid,value['planning_peer_uid'],value['browser_peer_uid'],value['history_uid']})!=4):
        raise ValueError('distinct dedicated service identities required')
    for name in ('history_socket','review_socket','browser_socket'):u.endpoint(value[name])
    if Path(value['review_socket']).parent==Path(value['browser_socket']).parent:
        raise ValueError('separate socket ACL directories required')
    if 'admission' in value:
        a=value['admission']
        if type(a) is not dict or set(a)!={'socket','issue_url'}:raise ValueError('exact admission reader configuration required')
        u.endpoint(a['socket'])
        if Path(a['socket']).parent in {Path(value['review_socket']).parent,Path(value['browser_socket']).parent}:
            raise ValueError('separate admission socket directory required')
        # Validate the URL without loading any credential or starting a listener.
        local('onboarding_operator_issue_http').Transport(a['issue_url'],value['app_user_id'],b'x'*32)
    if 'jarvis_review' in value:
        j=value['jarvis_review']
        if type(j) is not dict or set(j)!={'socket','peer_uid','app_user_id','origin_url','issue_url','scope_path'}:
            raise ValueError('exact Jarvis review configuration required')
        u.uid(j['peer_uid']);u.endpoint(j['socket']);local('onboarding_drafts').identifier(j['app_user_id'])
        if j['peer_uid'] in {uid,value['planning_peer_uid'],value['browser_peer_uid'],value['history_uid']} or j['app_user_id']==value['app_user_id']:
            raise ValueError('separate Jarvis review identity required')
        forbidden={Path(value['review_socket']).parent,Path(value['browser_socket']).parent}
        if 'admission' in value:forbidden.add(Path(value['admission']['socket']).parent)
        if Path(j['socket']).parent in forbidden or not Path(j['scope_path']).is_absolute():
            raise ValueError('separate Jarvis review socket and protected scopes required')
        local('hermes_planning_reader_http').Reader(j['origin_url'],j['issue_url'],j['app_user_id'],b'x'*32)
    a=value['access']
    if type(a) is not dict or set(a)!={'issuer','audience','email','origin'}:raise ValueError('exact operator access required')
    web('access').AccessConfig(**a)
    return value


@contextmanager
def journal(root):
    private=local('codex_runtime').private;root=private(root,True);path=private(root/'operator.sqlite3')
    fd=os.open(root/'operator.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_nlink!=1 or info.st_mode&0o077:
            raise ValueError('private operator lock required')
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        @contextmanager
        def connection():
            private(path);db=sqlite3.connect(path,timeout=5)
            db.execute('PRAGMA synchronous=FULL');db.execute('PRAGMA foreign_keys=ON')
            try:yield db
            except BaseException:db.rollback();raise
            finally:db.close()
        yield connection
    finally:os.close(fd)


def serve(value,root,planning_token,comment_token,issue_token=None,jarvis_token=None):
    if planning_token==comment_token:raise ValueError('distinct protected reader credentials required')
    if ('admission' in value) != (issue_token is not None) or (issue_token is not None and issue_token in (planning_token,comment_token)):
        raise ValueError('separate protected issue credential required')
    if ('jarvis_review' in value)!=(jarvis_token is not None) or (jarvis_token is not None and jarvis_token in (planning_token,comment_token,issue_token)):
        raise ValueError('separate Jarvis reader credential required')
    if os.geteuid()!=os.getuid() or os.getegid()!=os.getgid() or set(os.getgroups())-{os.getgid()}:
        raise ValueError('dedicated unprivileged operator identity required')
    c=configuration(value,os.getuid(),os.getgid());transport=local('onboarding_broker_unix');unix=transport.unix()
    reader=local('planning_reader_http').Reader(c['reader_origin_url'],c['reader_issue_url'],c['app_user_id'],planning_token)
    comments=local('onboarding_operator_comment_http').Transport(c['comment_url'],c['app_user_id'],comment_token)
    access=web('access').Access(web('access').AccessConfig(**c['access']))
    history=lambda message:unix.call(c['history_socket'],c['history_uid'],message)
    selected={key:c[key] for key in ('organization_id','app_user_id','team_id','human_ids','planning_peer_uid','scopes')}
    stop=threading.Event();previous=signal.getsignal(signal.SIGTERM)
    def terminate(_signum,_frame):stop.set()
    with journal(root) as connection:
        operator=local('onboarding_operator_service').assemble(selected,connection,access,reader,comments,history)
        browser=local('onboarding_operator_browser_unix').Broker(c['browser_peer_uid'],operator['browser'])
        acl=local('runtime_checkpoint_broker').acl_on_bound
        signal.signal(signal.SIGTERM,terminate)
        try:
            with ExitStack() as stack:
                review=stack.enter_context(transport.server(c['review_socket'],operator['review_broker'],on_bound=lambda path:acl(path,c['planning_peer_uid']),deadline_seconds=60))
                browser_server=stack.enter_context(transport.server(c['browser_socket'],browser,on_bound=lambda path:acl(path,c['browser_peer_uid']),deadline_seconds=60))
                servers=[review,browser_server]
                if 'admission' in c:
                    issue_transport=local('onboarding_operator_issue_http').Transport(c['admission']['issue_url'],c['app_user_id'],issue_token)
                    issue_reader=local('onboarding_linear_issue_reader').Reader(issue_transport,c['app_user_id'],c['organization_id'])
                    admission=local('onboarding_admission_service').assemble_history(operator,history,issue_reader)
                    servers.append(stack.enter_context(transport.server(c['admission']['socket'],admission,deadline_seconds=60)))
                if 'jarvis_review' in c:
                    j=c['jarvis_review'];jarvis=local('hermes_planning_reader_http').Reader(j['origin_url'],j['issue_url'],j['app_user_id'],jarvis_token)
                    resolver=local('hermes_planning_origin').Resolver(j['peer_uid'],c['organization_id'],j['app_user_id'],jarvis.origin,
                        local('hermes_planning_scope').Resolver(j['scope_path']))
                    broker=local('hermes_planning_review_broker').Broker(j['peer_uid'],resolver,jarvis.issue,connection,operator['history'].reader,c['scopes'],c['team_id'])
                    servers.append(stack.enter_context(transport.server(j['socket'],broker,on_bound=lambda path:acl(path,j['peer_uid']),deadline_seconds=60)))
                failures=[]
                def loop(server):
                    try:
                        while not stop.is_set():server.serve_once()
                    except BaseException:
                        failures.append(True);stop.set()
                workers=[threading.Thread(target=loop,args=(server,),daemon=True) for server in servers]
                for worker in workers:worker.start()
                try:stop.wait()
                finally:
                    stop.set()
                    for worker in workers:worker.join(60)
                    if any(worker.is_alive() for worker in workers):raise ValueError('operator worker did not stop')
                    if failures:raise ValueError('operator worker failed')
        finally:signal.signal(signal.SIGTERM,previous)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--config',required=True);parser.add_argument('--state',required=True)
    parser.add_argument('--planning-token',required=True);parser.add_argument('--comment-token',required=True);parser.add_argument('--issue-token');parser.add_argument('--initialize',action='store_true')
    parser.add_argument('--jarvis-token')
    args=parser.parse_args();os.environ.clear();os.environ.update(PATH='/usr/bin:/bin',HOME='/nonexistent',LANG='C.UTF-8');os.umask(0o077)
    try:
        protected=local('protected_config');value=configuration(protected.decode(args.config,require_root=True),os.getuid(),os.getgid())
        if args.initialize:
            import json
            print(json.dumps(initialize(args.state),sort_keys=True));return
        planning=protected.read(args.planning_token,maximum=257,require_root=True).strip()
        comment=protected.read(args.comment_token,maximum=257,require_root=True).strip()
        issue=protected.read(args.issue_token,maximum=257,require_root=True).strip() if args.issue_token else None
        jarvis=protected.read(args.jarvis_token,maximum=257,require_root=True).strip() if args.jarvis_token else None
        serve(value,Path(args.state),planning,comment,issue,jarvis)
    except Exception:parser.exit(1,'Private operator service refused; preserve configuration and journal for inspection.\n')


if __name__=='__main__':main()
