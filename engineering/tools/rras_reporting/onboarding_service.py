"""Compose the separately protected Codex planning components.

The host owns configuration, SQLite setup, credentials, Unix socket ACLs and
service hardening. This module does not install or activate a service.
"""
import importlib.util
from pathlib import Path
import threading
import time


def local(name):
    spec=importlib.util.spec_from_file_location('planning_service_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def initialize_empty(db):
    """Initialize a new private journal; never adopt a partially initialized one."""
    if db.execute("SELECT 1 FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' LIMIT 1").fetchone():
        raise ValueError('empty planning journal required')
    local('onboarding_sessions').Sessions.initialize(db)
    local('onboarding_runtime').Runtime.initialize(db)
    local('onboarding_issue_journal').IssueJournal.initialize(db)


def assemble(config,connection,reader_token,bridge_token,*,creator_token=None,reader=None,history_rpc=None,client_factory=None,clock=time.time):
    required={'runtime_policy','team_id','scopes','history_socket','history_uid','broker_socket','native_socket','native_peer_uid',
              'mcp_python','lock_path','reader_origin_url','reader_issue_url','listen_address','listen_port'}
    if type(config) is not dict or set(config) not in (required,required|{'issue_creator_url'}):
        raise ValueError('exact protected planning service configuration required')
    creation_enabled='issue_creator_url' in config
    if creation_enabled!=(creator_token is not None):raise ValueError('explicit issue creator and credential required')
    d=local('onboarding_drafts');d.identifier(config['team_id'])
    policy=config['runtime_policy']
    if type(policy) is not dict:raise ValueError('protected runtime policy required')
    org=d.identifier(policy.get('organization_id'));app=d.identifier(policy.get('app_user_id'))
    peer=policy.get('peer_uid')
    if type(peer) is not int or peer<1 or type(config['history_uid']) is not int or config['history_uid']<1:
        raise ValueError('explicit native and history identities required')
    if type(config['scopes']) is not list or not config['scopes'] or len(config['scopes'])>128:
        raise ValueError('explicit planning scopes required')
    scopes=[d.selected_scope(scope) for scope in config['scopes']]
    if len({(scope['kind'],scope['id']) for scope in scopes})!=len(scopes):raise ValueError('distinct scope grants required')
    if reader is None:reader=local('planning_reader_http').Reader(config['reader_origin_url'],config['reader_issue_url'],app,reader_token)
    u=local('onboarding_broker_unix').unix();u.uid(config['history_uid'])
    if type(config['native_peer_uid']) is not int or not 0<=config['native_peer_uid']<2**32-1:
        raise ValueError('exact native listener identity required')
    if history_rpc is None:history_rpc=lambda message:u.call(config['history_socket'],config['history_uid'],message)
    adapter=local('onboarding_history').HistoryAdapter(history_rpc,
        lambda organization,project:history_rpc(dict(method='planning_binding',organization_id=organization,linear_project_id=project)),
        lambda organization,linear,team,project,scope:history_rpc(dict(method='planning_reserve',organization_id=organization,
            linear_project_id=linear,team_id=team,project_id=project,scope=scope)),scopes)
    context=local('onboarding_runtime_context').Context(connection,reader,org,app,peer)
    grants={peer:dict(agent='codex',organization_id=org,team_id=config['team_id'],scopes=scopes)}
    registry=local('onboarding_sessions').Sessions(connection,grants,context.native,context.active,clock=clock)
    launch=local('onboarding_mcp').Launch(config['broker_socket'],__import__('os').getuid(),config['mcp_python'],allow_create=creation_enabled)
    if client_factory is None:
        client_factory=lambda:local('codex_runtime').SocketAppServer(config['native_socket'],config['native_peer_uid'],timeout=30)
    runtime=local('onboarding_runtime').Runtime(connection,policy,context.verify_event,registry,launch,client_factory,clock,config['lock_path'])
    try:
        journal=local('onboarding_issue_journal').IssueJournal(connection);journal.recover_after_exclusive_start()
        creator=local('planning_issue_create_http').Creator(config['issue_creator_url'],app,creator_token) if creation_enabled else None
        broker=local('onboarding_broker').Broker(grants,registry.lookup,reader.issue,adapter,
            issue_journal=journal if creator else None,
            issue_create=(lambda dispatch,selected,plan,proposal:creator.create(dispatch,plan,proposal)) if creator else None)
        http=local('onboarding_runtime_http').server(runtime,bridge_token,
            (config['listen_address'],config['listen_port']),verify_stop=context.verify_stop)
        return Service(runtime,broker,http,config['broker_socket'])
    except BaseException:
        runtime.close();raise


class Service:
    def __init__(self,runtime,broker,http,socket_path):
        self.runtime,self.broker,self.http,self.socket_path=runtime,broker,http,socket_path

    def serve(self,on_bound):
        if not callable(on_bound):raise ValueError('explicit installed socket ACL required')
        stop=threading.Event()
        with local('onboarding_broker_unix').server(self.socket_path,self.broker,on_bound=on_bound) as broker:
            def work():
                while not stop.is_set():broker.serve_once()
            worker=threading.Thread(target=work,daemon=True);worker.start()
            try:self.http.serve_forever()
            finally:stop.set();worker.join(5)

    def close(self):
        try:self.http.server_close()
        finally:self.runtime.close()
