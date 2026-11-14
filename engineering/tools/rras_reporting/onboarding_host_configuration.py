"""Build inactive v0.5 host configuration; no credentials or installation."""
import importlib.util
import ipaddress
from pathlib import Path


def local(name):
    spec=importlib.util.spec_from_file_location('onboarding_host_configuration_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def build(identities,access,n8n_port,gateway,release,project_id):
    fields={'organization_id','team_id','codex_app_user_id','jarvis_app_user_id','human_id'}
    if type(identities) is not dict or set(identities)!=fields:raise ValueError('exact verified identities required')
    d=local('onboarding_drafts')
    for value in identities.values():d.identifier(value)
    d.identifier(project_id)
    if len({identities['codex_app_user_id'],identities['jarvis_app_user_id'],identities['human_id']})!=3:
        raise ValueError('distinct human and agent identities required')
    if type(n8n_port) is not int or not 1024<=n8n_port<=65535:raise ValueError('private n8n port required')
    try:address=ipaddress.IPv4Address(gateway)
    except (ValueError,TypeError):raise ValueError('private bridge address required') from None
    if not any(address in ipaddress.IPv4Network(x) for x in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')):
        raise ValueError('private bridge address required')
    p=Path(release) if type(release) is str else Path('.')
    if not p.is_absolute() or not str(p).startswith('/opt/rras-engineering/releases/standardized-history-'):
        raise ValueError('fixed release path required')
    org=identities['organization_id'];team=identities['team_id'];codex=identities['codex_app_user_id'];jarvis=identities['jarvis_app_user_id']
    repo={'kind':'repository','id':'jarvis'};fallback={'kind':'non_git','id':'jarvis-non-git'};scopes=[repo,fallback]
    url='http://127.0.0.1:'+str(n8n_port)+'/webhook/'
    # The two identities need distinct root-owned copies: protected_config
    # deliberately refuses a group-readable file owned by another group.
    scopes_path='/etc/rras-engineering/onboarding-operator/jarvis-scopes.json'
    scope_map=dict(contract='hermes-planning-project-scopes.v1',projects={project_id:repo},fallback_scope=fallback)
    operator=dict(operator_uid=61182,operator_gid=61182,planning_peer_uid=61181,browser_peer_uid=993,history_uid=995,
        history_socket='/run/rras-engineering-history/service.sock',review_socket='/run/rras-onboard-review/review.sock',
        browser_socket='/run/rras-onboard-browser/browser.sock',organization_id=org,app_user_id=codex,team_id=team,
        human_ids=[identities['human_id']],scopes=scopes,reader_origin_url=url+'rras-planning-origin-'+codex,
        reader_issue_url=url+'rras-planning-issue-'+codex,comment_url=url+'rras-operator-comment-'+codex,access=access,
        admission=dict(socket='/run/rras-onboard-admission/admission.sock',issue_url=url+'rras-operator-issue-'+codex),
        jarvis_review=dict(socket='/run/rras-onboard-jarvis/review.sock',peer_uid=61180,app_user_id=jarvis,
            origin_url=url+'rras-jarvis-planning-origin-'+jarvis,issue_url=url+'rras-jarvis-planning-issue-'+jarvis,scope_path=scopes_path))
    browser=dict(browser_uid=993,browser_gid=993,operator_uid=61182,operator_socket=operator['browser_socket'],
        bind=str(address),port=8769,access=access,path_prefix='/engineering-approval')
    jarvis_config=dict(organization_id=org,app_user_id=jarvis,team_id=team,peer_uid=61180,scopes=scopes,
        history_socket=operator['history_socket'],history_uid=995,reader_origin_url=operator['jarvis_review']['origin_url'],
        reader_issue_url=operator['jarvis_review']['issue_url'],listen_address=str(address),listen_port=8768,
        issue_creator_url=url+'rras-jarvis-planning-create-'+jarvis,
        review_socket=operator['jarvis_review']['socket'],review_peer_uid=61182)
    codex_config=dict(runtime_policy=dict(organization_id=org,app_user_id=codex,peer_uid=991,
        cwd='/srv/rras-codex-planning/workspace',planning_authorized=False,
        authority_reference='Inactive staged policy; separate authorization required.'),team_id=team,scopes=scopes,
        history_socket=operator['history_socket'],history_uid=995,broker_socket='/run/rras-codex-planning/broker.sock',
        native_socket='/run/rras-codex-planning-native/app.sock',native_peer_uid=0,mcp_python=str(p/'venv/bin/python'),
        lock_path='/var/lib/rras-codex-planner/state/planning.lock',reader_origin_url=operator['reader_origin_url'],
        reader_issue_url=operator['reader_issue_url'],listen_address=str(address),listen_port=8767,
        issue_creator_url=url+'rras-planning-create-'+codex,review_socket=operator['review_socket'],review_peer_uid=61182)
    local('onboarding_operator_entry').configuration(operator,61182,61182)
    local('onboarding_attestation_web_entry').configuration(browser,993,993)
    return dict(operator=operator,browser=browser,jarvis=jarvis_config,codex=codex_config,scopes=scope_map)
