"""Actual Git/SQLite and bounded harmless subprocesses, fake systemd/account only."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch
import pytest
import test_managed_events as managed
from test_workflow_finish import case
from test_workflow_publication import pubcase
from test_validation_workspace import staged


def pytest_generate_tests(metafunc):
    if 'case' in metafunc.fixturenames:
        metafunc.parametrize('case',[{'publication_remote':'git@github.com:fixture/library.git'}],indirect=True)


@pytest.fixture
def execution(staged):
    s=staged;s.stage();s.x.package.chmod(0o755);(s.x.package/'independent-validation.json').unlink();s.x.package.chmod(0o555)
    m=managed.module('validation_execution');actual=m.local
    reader=SimpleNamespace(root_bytes=lambda path,limit:Path(path).read_bytes())
    modules={'validation_workspace':s.m,'workflow_finish':s.x.c.f,'approved_launch':s.x.c.x.l,
             'publication_custody':reader,'managed_events':s.x.c.x.e}
    calls=[];answer={'service_exit':0,'capture_complete':True,'interruption':None,'output':b'PRIVATE_LOG_SENTINEL'}
    def run(argv,timeout):calls.append(argv);return dict(answer)
    with patch.object(m,'local',side_effect=lambda name:modules.get(name) or actual(name)),patch.object(m,'account'),patch.object(m,'bounded_run',side_effect=run):
        def invoke(name):
            with patch.object(m.os,'getuid',return_value=0),patch.object(m.os,'geteuid',return_value=0):
                if name=='release':s.x.package.chmod(0o755) # UID1000 fixture only; real root owns package.
                try:return getattr(m,name)(s.x.c.custody,s.x.package,s.root)
                finally:s.x.package.chmod(0o555)
        yield SimpleNamespace(m=m,s=s,answer=answer,calls=calls,execute=lambda:invoke('execute'),record=lambda:invoke('record'),load=lambda:invoke('load'),release=lambda:invoke('release'))


def test_independent_result_recording_and_no_reexecution(execution):
    x=execution;r=x.execute();assert r['outcome']=='succeeded' and not r['task_success_established']
    _,_,result=x.load();assert result['plan']['identity']['commit']==x.s.x.proof['commit']
    assert len(x.calls)==1 and any(a.startswith('BindReadOnlyPaths=') for a in x.calls[0])
    with pytest.raises(ValueError):x.execute()
    x.record();count=len(x.s.x.c.x.events());x.record();assert len(x.s.x.c.x.events())==count
    event=x.s.x.c.x.events()[-1]
    assert event['event_type']=='validation.finished' and event['provenance']['kind']=='observed'
    assert event['outcome']=='succeeded'
    assert b'PRIVATE_LOG_SENTINEL' not in x.s.x.c.x.store.artifact(event['artifacts'][0]['sha256'])
    assert 'PRIVATE_LOG_SENTINEL' not in json.dumps(x.s.x.c.x.store.status())
    assert x.s.x.c.x.store.status()['work_items'][0]['attempts'][0]['terminal_claim']['provenance']=='imported'
    assert len(x.calls)==1
    assert b'PRIVATE_LOG_SENTINEL' not in (x.s.x.c.custody/x.m.RESULT).read_bytes()


@pytest.mark.parametrize('code',[1,9,-9])
def test_nonzero_service_attempt_cannot_pass(execution,code):
    x=execution;x.answer['service_exit']=code
    assert x.execute()['outcome']=='failed';assert x.record()['outcome']=='failed'


@pytest.mark.parametrize('reason',['client_timeout','output_limit','client_error'])
def test_interrupted_capture_is_uncertain_and_fenced(execution,reason):
    x=execution;x.answer.update(service_exit=None,capture_complete=False,interruption=reason)
    assert x.execute()['outcome']=='uncertain';assert x.record()['outcome']=='uncertain'
    with pytest.raises(ValueError):x.execute()
    assert len(x.calls)==1


def test_busy_slot_does_not_consume_fence(execution):
    x=execution
    with patch.object(x.s.x.c.x.l,'slot',side_effect=ValueError('busy')),pytest.raises(ValueError):x.execute()
    assert not (x.s.x.c.custody/x.m.STARTED).exists() and not x.calls


def test_stop_uncertainty_is_retained(execution):
    x=execution
    with patch.object(x.s.x.c.x.l,'slot',side_effect=[None,ValueError('busy')]):
        assert x.execute()['outcome']=='uncertain'
    assert x.record()['outcome']=='uncertain'
    with pytest.raises(ValueError):x.execute()


def test_partial_result_write_keeps_one_use_fence(execution):
    x=execution;a=x.m.local('activity');actual=a.absent
    def write(path,raw):
        if Path(path).name==x.m.RESULT:raise OSError('fixture disk failure')
        return actual(path,raw)
    original=x.m.local
    with patch.object(a,'absent',side_effect=write),patch.object(x.m,'local',side_effect=lambda name:a if name=='activity' else original(name)),pytest.raises(OSError):x.execute()
    assert (x.s.x.c.custody/x.m.STARTED).exists()
    with pytest.raises(ValueError):x.execute()
    assert len(x.calls)==1


@pytest.mark.parametrize('member',['output','fence','result'])
def test_changed_custody_refused_before_journal(execution,member):
    x=execution;x.execute();root=x.s.x.c.custody
    path=root/({'output':x.m.OUTPUT,'fence':x.m.STARTED,'result':x.m.RESULT}[member])
    if member=='output':path.write_bytes(b'tampered')
    else:
        data=json.loads(path.read_bytes())
        if member=='fence':data['plan_sha256']='0'*64
        else:data['classification']['outcome']='failed'
        path.write_text(json.dumps(data))
    count=len(x.s.x.c.x.events())
    with pytest.raises(ValueError):x.record()
    assert len(x.s.x.c.x.events())==count


def test_exclusive_fence_is_not_idempotent(tmp_path):
    m=managed.module('validation_execution');p=tmp_path/'fence';m.exclusive(p,b'exact')
    with pytest.raises(FileExistsError):m.exclusive(p,b'exact')
    assert p.read_bytes()==b'exact'


def test_bounded_client_captures_harmless_output():
    m=managed.module('validation_execution')
    r=m.bounded_run([sys.executable,'-I','-c','print("fixture")'],5)
    assert r=={'service_exit':0,'capture_complete':True,'interruption':None,'output':b'fixture\n'}


def test_bounded_client_refuses_unbounded_output():
    m=managed.module('validation_execution')
    with patch.object(m,'OUTPUT_LIMIT',1024):
        r=m.bounded_run([sys.executable,'-I','-c','import os;os.write(1,b"x"*8192)'],5)
    assert len(r['output'])==1024 and r['interruption']=='output_limit' and r['service_exit'] is None


def test_bounded_client_timeout_does_not_claim_service_stop():
    m=managed.module('validation_execution')
    r=m.bounded_run([sys.executable,'-I','-c','import time;time.sleep(5)'],0.05)
    assert not r['capture_complete'] and r['service_exit'] is None and r['interruption']=='client_timeout'


def test_read_only_mount_contract_has_no_writable_candidate():
    m=managed.module('post_validation');p=dict(unit=m.UNIT,uid=996,network=False,credentials=False,
        checkout_mode='baseline_with_unstaged_review_tree',argv=['/usr/bin/git','diff','--check'],timeout_seconds=30)
    argv=m.service_argv(p,'/run/rras-validation/repo','/var/lib/rras-workflow/stages/fixture/repo')
    assert 'BindReadOnlyPaths=/var/lib/rras-workflow/stages/fixture/repo:/run/rras-validation/repo' in argv
    assert not any(a.startswith('ReadWritePaths=') for a in argv)
    assert 'GIT_OPTIONAL_LOCKS=0' in argv and 'GIT_CONFIG_VALUE_0=/run/rras-validation/repo' in argv
    assert 'GIT_CONFIG_COUNT=1' in argv


@pytest.mark.parametrize('source',['/tmp/with space/repo','/tmp/a:b/repo','relative','/tmp/../other'])
def test_bind_argument_injection_is_refused(source):
    m=managed.module('post_validation');p=dict(unit=m.UNIT,uid=996,network=False,credentials=False,
        checkout_mode='baseline_with_unstaged_review_tree',argv=['/bin/true'],timeout_seconds=30)
    with pytest.raises(ValueError):m.service_argv(p,'/run/rras-validation/repo',source)


def test_managed_package_stays_blocked_until_recorded_success_released(execution):
    x=execution;hf=x.s.x.p.local('publication_handoff')
    with pytest.raises(FileNotFoundError):hf.read(x.s.x.package)
    x.execute();assert x.release()['released_validation_proof']
    record,_=hf.read(x.s.x.package)
    proof=hf.require_validation(record,x.s.x.package)
    assert proof['commit']==x.s.x.proof['commit']
    assert not proof['task_success_established'] and not proof['merge_authorized']
    x.release();assert len(x.calls)==1


def test_failed_check_cannot_release_publication_proof(execution):
    x=execution;x.answer['service_exit']=1;x.execute()
    with pytest.raises(ValueError):x.release()
    assert not (x.s.x.package/'independent-validation.json').exists()


def test_journal_failure_blocks_release_without_execution_retry(execution):
    x=execution;x.execute()
    with patch.object(x.m,'record',side_effect=OSError('fixture journal offline')),pytest.raises(OSError):x.release()
    assert not (x.s.x.package/'independent-validation.json').exists()
    x.release();assert len(x.calls)==1


def test_wrong_commit_proof_refused_even_with_success_word(execution):
    x=execution;x.execute();x.release();p=x.s.x.package/'independent-validation.json'
    p.chmod(0o600);d=json.loads(p.read_bytes());d['commit']='0'*40;p.write_text(json.dumps(d));p.chmod(0o444)
    hf=x.s.x.p.local('publication_handoff')
    with pytest.raises(ValueError):hf.read(x.s.x.package)


def test_managed_publication_capture_refused_without_validation(execution):
    x=execution
    with pytest.raises(FileNotFoundError):x.s.x.capture(x.s.x.root/'premature-publication')


@pytest.mark.parametrize('uid,gid,groups',[(0,996,[996]),(996,0,[996]),(996,996,[996,999])])
def test_identity_or_supplementary_group_change_refused(uid,gid,groups):
    m=managed.module('validation_execution')
    with patch.object(m.pwd,'getpwnam',return_value=SimpleNamespace(pw_name='fixture',pw_uid=uid,pw_gid=gid)),patch.object(m.os,'getgrouplist',return_value=groups),pytest.raises(ValueError):m.account()


def test_start_client_failure_is_uncertain_and_not_retried(execution):
    x=execution
    with patch.object(x.m,'bounded_run',side_effect=OSError('fixture client spawn failure')):
        assert x.execute()['outcome']=='uncertain'
    assert x.record()['outcome']=='uncertain'
    with pytest.raises(ValueError):x.execute()


def test_legacy_handoff_is_explicitly_outside_managed_validation_gate():
    m=managed.module('publication_handoff')
    assert m.require_validation({'schema_version':1},'/unused-fixture') is None


def test_duplicate_finish_custody_cannot_rearm_same_coding_launch(execution):
    import shutil
    x=execution;x.execute();other=x.s.x.root/'duplicated-finish'
    shutil.copytree(x.s.x.c.custody,other)
    # Even after removing local execution evidence, the original root job fence
    # remains exclusive across copies and different stage locations.
    for name in (x.m.STARTED,x.m.RESULT,x.m.OUTPUT):(other/name).unlink()
    with patch.object(x.m.os,'getuid',return_value=0),patch.object(x.m.os,'geteuid',return_value=0),pytest.raises(FileExistsError):
        x.m.execute(other,x.s.x.package,x.s.root)
    assert len(x.calls)==1
