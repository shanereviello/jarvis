"""Inert validation contracts; no systemd/model/network calls or host mutation."""
import pytest
import test_managed_events as managed
from test_workflow_finish import case


@pytest.fixture
def contract(case):
    m=managed.module('post_validation');c=case
    p=dict(repository_id=c.review['request']['repository_id'],task_id=c.review['request']['task_id'],
        branch=c.review['review_branch'],baseline=c.review['baseline_commit'],commit='a'*40,export_id='b'*64)
    return m,c,p,m.plan(c.review,p,'c'*64)


def test_admitted_recipe_and_exact_review_bound(contract):
    m,c,p,plan=contract
    assert plan['argv']==c.review['request']['validation_argv']
    assert plan['identity']['commit']==p['commit']
    assert plan['checkout_mode']=='baseline_with_unstaged_review_tree'
    assert not plan['execution_authorized'] and not plan['publication_authorized']
    c.review['request']['validation_argv'].append('MUTATED')
    assert 'MUTATED' not in plan['argv']


@pytest.mark.parametrize('field',['repository_id','task_id','branch','baseline','commit','export_id'])
def test_changed_prepared_association_refused(contract,field):
    m,c,p,plan=contract;p[field]='invalid'
    with pytest.raises(ValueError):m.plan(c.review,p,'c'*64)


def test_model_cannot_select_validation_command(contract):
    m,c,p,plan=contract;c.review['request']['validation_argv']=['/bin/true']
    with pytest.raises(ValueError):m.plan(c.review,p,'c'*64)


def test_service_uses_same_slot_no_credentials_or_network(contract):
    m,c,p,plan=contract;argv=m.service_argv(plan,'/var/lib/rras-coding-tasks/validation-test/repo')
    assert argv[argv.index('--unit')+1]=='rras-coding-task.service'
    assert 'PrivateNetwork=yes' in argv and 'ProtectSystem=strict' in argv
    assert 'User=jarvis-codex-engineering' in argv
    assert not any('LoadCredential' in x or 'API_KEY' in x or 'manual_runner' in x for x in argv)
    assert argv[-len(plan['argv']):]==plan['argv']
    assert argv[argv.index('/usr/bin/env')+1]=='-i'


@pytest.mark.parametrize('path',['/tmp/repo','/var/lib/rras-coding-tasks','/var/lib/rras-coding-tasks/../other','/var/lib/rras-coding-tasks/a b','relative'])
def test_unsafe_workspace_refused(contract,path):
    m,c,p,plan=contract
    with pytest.raises(ValueError):m.service_argv(plan,path)


@pytest.mark.parametrize('key,value',[('network',True),('credentials',True),('uid',0),('unit','other.service'),('timeout_seconds',True),('timeout_seconds',61),('argv',['relative']),('argv',['/bin/true','\0']),('argv',['/bin/echo','$HOME']),('argv',['/bin/echo','%n'])])
def test_weakened_service_contract_refused(contract,key,value):
    m,c,p,plan=contract;plan[key]=value
    with pytest.raises(ValueError):m.service_argv(plan,'/var/lib/rras-coding-tasks/validation-test/repo')


def observation(m,plan):
    return dict(plan_sha256=m.local('activity').digest(m.local('activity').encoded(plan)),service_exit=0,
        host_stop_verified=True,tree_before='d'*40,tree_after='d'*40,expected_tree='d'*40)


@pytest.mark.parametrize('exit_code,outcome',[(0,'succeeded'),(1,'failed'),(-9,'failed')])
def test_host_result_is_separate_mechanical_check(contract,exit_code,outcome):
    m,c,p,plan=contract;o=observation(m,plan);o['service_exit']=exit_code;r=m.observed_result(plan,o)
    assert r['outcome']==outcome and r['independently_executed_check']
    assert not any(r[k] for k in ('task_success_established','human_acceptance','publication_authorized','retry_authorized'))


@pytest.mark.parametrize('key,value',[('host_stop_verified',False),('service_exit',None),('tree_before',None),('tree_after','e'*40),('expected_tree',None)])
def test_missing_or_changed_host_facts_preserve_uncertainty(contract,key,value):
    m,c,p,plan=contract;o=observation(m,plan);o[key]=value
    assert m.observed_result(plan,o)['outcome']=='uncertain'


@pytest.mark.parametrize('key,value',[('plan_sha256','e'*64),('service_exit',False),('host_stop_verified',1),('tree_after','invalid')])
def test_invalid_host_observation_refused(contract,key,value):
    m,c,p,plan=contract;o=observation(m,plan);o[key]=value
    with pytest.raises(ValueError):m.observed_result(plan,o)


def test_rendered_environment_clears_inherited_provider_variables(contract):
    import subprocess
    m,c,p,plan=contract;plan['argv']=['/usr/bin/env']
    argv=m.service_argv(plan,'/var/lib/rras-coding-tasks/validation-test/repo')
    # Execute only the harmless env segment, never systemd or a repository recipe.
    result=subprocess.run(argv[argv.index('/usr/bin/env'):],env={'OPENAI_API_KEY':'fake-sentinel','GITHUB_TOKEN':'fake-sentinel'},capture_output=True,text=True,check=True)
    assert 'fake-sentinel' not in result.stdout
    assert set(line.split('=',1)[0] for line in result.stdout.splitlines())=={
        'PATH','LANG','HOME','PYTHONDONTWRITEBYTECODE','GIT_CONFIG_NOSYSTEM','GIT_CONFIG_GLOBAL','GIT_TERMINAL_PROMPT'}
