"""Compose a separate protected Jarvis planning service; never install it."""
import importlib.util
from pathlib import Path


def local(name):
    spec=importlib.util.spec_from_file_location('hermes_planning_service_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def assemble(config,reader_token,bridge_token,resolve_scope,*,reader=None,history_rpc=None):
    fields={'organization_id','app_user_id','team_id','peer_uid','scopes','history_socket','history_uid',
            'reader_origin_url','reader_issue_url','listen_address','listen_port'}
    if type(config) is not dict or set(config)!=fields or not callable(resolve_scope):
        raise ValueError('exact protected Jarvis planning configuration required')
    if reader_token==bridge_token:raise ValueError('distinct reader and bridge credentials required')
    d=local('onboarding_drafts')
    for key in ('organization_id','app_user_id','team_id'):d.identifier(config[key])
    unix=local('onboarding_broker_unix').unix();unix.uid(config['peer_uid']);unix.uid(config['history_uid'])
    unix.endpoint(config['history_socket'])
    if type(config['scopes']) is not list or not 1<=len(config['scopes'])<=128:
        raise ValueError('explicit planning scopes required')
    scopes=[d.selected_scope(scope) for scope in config['scopes']]
    if len({(scope['kind'],scope['id']) for scope in scopes})!=len(scopes):raise ValueError('distinct planning scopes required')
    if reader is None:
        reader=local('hermes_planning_reader_http').Reader(config['reader_origin_url'],config['reader_issue_url'],config['app_user_id'],reader_token)
    if history_rpc is None:
        history_rpc=lambda message:unix.call(config['history_socket'],config['history_uid'],message)
    adapter=local('onboarding_history').HistoryAdapter(history_rpc,
        lambda org,project:history_rpc(dict(method='planning_binding',organization_id=org,linear_project_id=project)),
        lambda org,linear,team,project,scope:history_rpc(dict(method='planning_reserve',organization_id=org,
            linear_project_id=linear,team_id=team,project_id=project,scope=scope)),scopes)
    resolver=local('hermes_planning_origin').Resolver(config['peer_uid'],config['organization_id'],config['app_user_id'],reader.origin,resolve_scope)
    grants={config['peer_uid']:dict(agent='jarvis',organization_id=config['organization_id'],team_id=config['team_id'],scopes=scopes)}
    broker=local('hermes_planning_broker').Broker(grants,resolver,reader.issue,adapter)
    return local('hermes_planning_http').server(broker,config['peer_uid'],bridge_token,
        (config['listen_address'],config['listen_port']))
