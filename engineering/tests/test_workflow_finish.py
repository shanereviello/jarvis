"""Real disposable journals/launch receipts; no worker, service or network calls."""
import copy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import pytest
import test_managed_events as managed


@pytest.fixture
def case(request):
    x=managed.ManagedTests('runTest');x.setUp();f=managed.module('workflow_finish');patches=[]
    try:
        remote=getattr(request,'param',{}).get('publication_remote')
        if remote:
            x.registration['publication']['remote']=remote;x.registration['source']['remote']=remote;x.bind();x.config['registration']=x.registration;x.save_config()
        captured=x.capture();auth=x.approve(captured['review_id']);host,_=x.invoke(auth['authorization_id'])
        review=x.approval.read_review(x.state,captured['review_id']);root=Path(host['work'])
        context={'schema_version':1,'task':'t_finish','run_id':1,'home':str(root/'home/profiles/rras-engineering'),'board':str(root/'home/kanban/kanban.db'),'python':f.local('native_task_cli').TRUSTED_PYTHON}
        evidence={'scope':'native-manual-admitted-task','success':True,'lifecycle_mutated_by_runner':False,'native_task':'t_finish','native_run':1,'workspace':str(root.parent/'repo/.worktrees/finish'),'phase':'finished','wait':{'success':True,'worker_stop_verified':True,'exit_code':0,'native_status':'done','outcome':'completed'},'validation_exit':0,'validation_stop_verified':True,'mechanical_validation':'passed'}
        files={'changes.patch':b'fixture patch','additional-artifact-1.json':x.a.encoded(review['request'])}
        manifest={'task':{'task_id':review['request']['task_id'],'repository_id':review['request']['repository_id'],'baseline_commit':review['baseline_commit']},'head_commit':review['baseline_commit'],'worktree':evidence['workspace'],'binding':{'hermes_task':'t_finish','hermes_run':'1'},'files':{k:{'sha256':x.a.digest(v),'size_bytes':len(v)} for k,v in files.items()}}
        export_id=x.a.digest(x.a.encoded(manifest));directory=root/'index'/review['request']['task_id']/'exports'/export_id
        evidence['export']={'export_id':export_id,'path':str(directory)}
        reads={root/'evidence.json':x.a.encoded(evidence),root/'native-task-context.json':x.a.encoded(context),directory/'manifest.json':x.a.encoded(manifest)}
        reads.update({directory/k:v for k,v in files.items()});custody=x.root/'finish-custody';actual=f.local
        modules={'operator_control':managed.m,'managed_events':x.e,'publication_capture':SimpleNamespace(worker_bytes=lambda path,limit:reads[Path(path)]),'publication_custody':SimpleNamespace(root_bytes=lambda path,limit:Path(path).read_bytes()),'approved_launch':x.l}
        patches=[patch.object(f,'local',side_effect=lambda name:modules.get(name) or actual(name)),patch.object(x.l,'trusted',side_effect=lambda p:Path(p)),patch.object(x.l,'slot')]
        for p in patches:p.start()
        def capture():return f.capture(x.state,auth['authorization_id'],custody)
        def record():
            with patch.object(f.os,'getuid',return_value=0),patch.object(f.os,'geteuid',return_value=0):return f.record(custody)
        yield SimpleNamespace(f=f,x=x,auth=auth,review=review,host=host,root=root,evidence=evidence,context=context,reads=reads,custody=custody,capture=capture,record=record,directory=directory)
    finally:
        for p in reversed(patches):p.stop()
        x.doCleanups()


def update(c):c.reads[c.root/'evidence.json']=c.x.a.encoded(c.evidence)
def failed_host(c):
    (c.x.state/(c.auth['authorization_id']+'.result.json')).write_bytes(c.x.a.encoded(dict(c.host,service_exit=1)))


def test_completion_validation_imported_and_replay_idempotent(case):
    c=case;assert c.capture()['terminal_claim'];before=len(c.x.events());assert c.record()['outcome']=='succeeded'
    events=c.x.events()[before:]
    assert [r['event_type'] for r in events]==['artifact.recorded','validation.finished','attempt.finished']
    assert all(r['provenance']['kind']=='imported' for r in events)
    status=c.x.store.status()['work_items'][0]
    assert status['attempts'][0]['terminal_claim']['provenance']=='imported' and status['release_status']=='not_inferred'
    assert not c.record()['publication_authorized'] and len(c.x.events())==before+3
    with pytest.raises(ValueError):c.capture()


def test_failed_validation_recorded_without_success(case):
    c=case;c.evidence.update(success=False,validation_exit=1,mechanical_validation='failed');update(c);failed_host(c)
    assert c.capture()['outcome']=='failed' and c.record()['outcome']=='failed'


def test_preflight_failure_stays_unfinished(case):
    c=case;c.evidence={'scope':'native-manual-admitted-task','success':False,'phase':'preflight','lifecycle_mutated_by_runner':False};update(c);failed_host(c)
    assert c.capture()['outcome']=='uncertain' and not c.record()['terminal_claim']
    assert c.x.store.status()['work_items'][0]['attempts'][0]['state']=='unfinished'


@pytest.mark.parametrize('kind',['native_run','workspace','boolean_exit','wait','service_exit','export','context_path','validation_stop'])
def test_inconsistent_claim_refused_before_custody(case,kind):
    c=case
    if kind=='native_run':c.evidence['native_run']=2
    if kind=='workspace':c.evidence['workspace']='/unrelated/.worktrees/task'
    if kind=='boolean_exit':c.evidence['validation_exit']=False
    if kind=='wait':c.evidence['wait']['native_status']='failed'
    if kind=='service_exit':failed_host(c)
    if kind=='export':c.evidence.pop('export')
    if kind=='context_path':
        c.context['board']='/unrelated/kanban.db';c.reads[c.root/'native-task-context.json']=c.x.a.encoded(c.context)
    if kind=='validation_stop':c.evidence['validation_stop_verified']=False
    update(c)
    with pytest.raises(ValueError):c.capture()
    assert not c.custody.exists()


def test_second_slot_check_blocks_capture(case):
    c=case
    with patch.object(c.x.l,'slot',side_effect=[None,ValueError('busy fixture')]),pytest.raises(ValueError):c.capture()
    assert not c.custody.exists()


def test_export_bytes_tampering_refused(case):
    c=case;c.reads[c.directory/'changes.patch']=b'changed'
    with pytest.raises(ValueError):c.capture()
    assert not c.custody.exists()


def test_custody_tampering_refused(case):
    c=case;c.capture();(c.custody/'evidence.json').write_bytes(b'{}')
    with pytest.raises(ValueError):c.record()
    assert not any(e['event_type']=='attempt.finished' for e in c.x.events())


def test_partial_journal_replay_repairs_without_service_or_worker(case):
    c=case;c.capture();real=c.x.store.append;failures=[]
    def append(*args,**kwargs):
        t=kwargs.get('transition')
        if t and t[0]['event_type']=='attempt.finished' and not failures:
            failures.append(True);raise OSError('fixture disk failure')
        return real(*args,**kwargs)
    with patch.object(c.x.e,'journal',return_value=c.x.store),patch.object(c.x.store,'append',side_effect=append):
        with pytest.raises(OSError):c.record()
        before=len(c.x.events());c.record()
    assert len(c.x.events())==before+1


def test_worker_and_control_evidence_unchanged(case):
    c=case;before={p:p.read_bytes() for p in c.x.state.iterdir() if p.is_file()};worker=copy.deepcopy(c.reads)
    c.capture();c.record();assert c.reads==worker
    assert {p:p.read_bytes() for p in c.x.state.iterdir() if p.is_file()}==before


def test_configuration_revocation_allows_historical_recording(case):
    c=case;c.capture();c.x.config_path.write_text('{}');assert c.record()['recorded']


def test_projection_omits_report_private_content(case):
    c=case;c.evidence['private_note']='NEVER_SHARED_REPORT';update(c);c.capture();c.record()
    output=c.x.root/'view.json';c.x.store.publish_jarvis(output,c.x.work['work_item_id']);raw=output.read_bytes()
    assert b'NEVER_SHARED_REPORT' not in raw and str(c.root).encode() not in raw and b'imported' in raw


def test_root_required(case):
    c=case;c.capture()
    with patch.object(c.f.os,'getuid',return_value=1000),pytest.raises(ValueError):c.f.record(c.custody)


def test_nonterminal_native_status_remains_uncertain(case):
    c=case;c.evidence.update(success=False);c.evidence['wait'].update(success=False,native_status='in_progress',outcome='failed');update(c);failed_host(c)
    assert c.capture()['outcome']=='uncertain' and not c.record()['terminal_claim']


def test_changed_report_cannot_replace_existing_finish_claim(case):
    c=case;c.capture();c.record()
    other=c.x.root/'different-custody'
    c.evidence['private_note']='changed report';update(c)
    c.f.capture(c.x.state,c.auth['authorization_id'],other)
    with patch.object(c.f.os,'getuid',return_value=0),patch.object(c.f.os,'geteuid',return_value=0),pytest.raises(ValueError):c.f.record(other)
    assert len([e for e in c.x.events() if e['event_type']=='attempt.finished'])==1
