"""A coder receives exact retained governing text, scope and acceptance criteria."""
import copy
import pytest
from test_reporting_runtime_reporting import setup,m,projects,store,reporting
from test_reporting_codex_runtime import m as runtime_module,Client,uid
from test_history_projects import save,designate,submit,read,REPO,P1
from test_history_reporting import request as history_request


def bundle(tmp_path,projects):
    policy,config,spool,reporter,request=setup(tmp_path,projects)
    value=m.local('runtime_task_context').from_reads(config['scope'],config['contexts'][uid(3)],lambda query:projects.read(config['scope'],query))
    return policy,config,reporter,request,value


def test_exact_scoped_snapshot_supplies_work_criteria_and_architecture(tmp_path,projects,reporting):
    policy,config,reporter,request,value=bundle(tmp_path,projects)
    config['task_contexts']={uid(3):value};reporter=m.Reporter(config,policy);client=Client()
    runtime=runtime_module.Runtime(tmp_path/'runtime',policy,create=True,reporter=reporter,client_factory=lambda *a:client)
    try:
        runtime.dispatch(request);params=next(p for method,p in client.calls if method=='thread/start')
        assert value['architecture_markdown'] in params['developerInstructions']
        assert value['work_definition']['acceptance_criteria'][0]['description'] in params['developerInstructions']
        assert config['contexts'][uid(3)]['architecture']['markdown_sha256'] in params['developerInstructions']
        assert 'not independent human authentication' in params['developerInstructions']
        assert value['source_snapshot']['sha256'] not in params['developerInstructions']
    finally:runtime.close()


@pytest.mark.parametrize('change',['markdown','work','assignment','designation','snapshot'])
def test_changed_or_unbound_contract_refused_before_generation(tmp_path,projects,reporting,change):
    policy,config,reporter,request,value=bundle(tmp_path,projects);bad=copy.deepcopy(value)
    if change=='markdown':bad['architecture_markdown']+='changed'
    if change=='work':bad['work_definition']['objective']='changed'
    if change=='assignment':bad['context']['work']['assignment_sha256']='9'*64
    if change=='designation':bad['governing_designation']['version']+=1
    if change=='snapshot':bad['source_snapshot']={}
    config['task_contexts']={uid(3):bad}
    with pytest.raises(ValueError):m.Reporter(config,policy)


def test_real_document_larger_than_message_limit_is_retained_without_truncation(tmp_path,projects,reporting):
    original=read(projects);markdown='# Agreed large fixture\n'+('Selected architecture details.\n'*2600)+'END-OF-EXACT-ARCHITECTURE\n'
    assert len(markdown.encode())>runtime_module.MAX_MESSAGE
    save(projects,2,markdown);designate(projects,2)
    work=projects.read(REPO,dict(view='work',work_id='wrk_'+'1'*32))
    submit(projects,'membership.designate',dict(work_item_id=work['work']['work_item_id'],expected_assignment_sha256=work['assignment']['assignment_sha256'],
        architecture_version=2,reason='Synthetic adopted second design'))
    policy,config,spool,reporter,request=setup(tmp_path,projects)
    project=read(projects);document=project['architecture'][-1];ctx=config['contexts'][uid(3)]
    ctx['architecture']={key:document[key] for key in ('document_id','version','markdown_sha256')}
    ctx['work']['assignment_sha256']=projects.read(REPO,dict(view='work',work_id=ctx['work']['work_item_id']))['assignment']['assignment_sha256']
    policy['issues'][uid(3)].update(architecture_version=2,architecture_sha256=document['markdown_sha256']);request['binding']=policy['issues'][uid(3)]
    value=m.local('runtime_task_context').from_reads(REPO,ctx,lambda query:projects.read(REPO,query));config['task_contexts']={uid(3):value}
    reporter=m.Reporter(config,policy);client=Client();runtime=runtime_module.Runtime(tmp_path/'runtime',policy,create=True,reporter=reporter,client_factory=lambda *a:client)
    try:
        runtime.dispatch(request);params=next(p for method,p in client.calls if method=='thread/start')
        assert params['developerInstructions'].endswith(markdown)
        assert len(runtime_module.encoded(params))<runtime_module.MAX_FRAME
    finally:runtime.close()
