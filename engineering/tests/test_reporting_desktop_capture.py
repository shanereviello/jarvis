"""Synthetic desktop lifecycle events and passive capture delivery."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest
from test_reporting_capture_intake import store,projects,evidence,reporting,sender,events
from test_reporting_capture_collectors import fixtures

ROOT=Path(__file__).resolve().parents[1]/'tools/rras_reporting'
spec=importlib.util.spec_from_file_location('desktop_capture_test',ROOT/'desktop_capture.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


@pytest.fixture
def selected(tmp_path):
    for name in ('registry','native','workspace'): (tmp_path/name).mkdir(mode=0o700)
    m.intake.Spool(tmp_path/'spool',create=True)
    binary=os.environ.get('SHRR_SPECSTORY_FIXTURE_BINARY',str(tmp_path/'binary'))
    value=dict(contract='engineering-desktop-capture.v1',registry=str(tmp_path/'registry'),spool=str(tmp_path/'spool'),
        native_root=str(tmp_path/'native'),binary=str(Path(binary).resolve()),service_socket=str(tmp_path/'service.sock'),service_uid=995,
        scope=dict(kind='repository',id='jarvis'),workspaces=[str(tmp_path/'workspace')],authorization_reference='synthetic fixture only')
    path=tmp_path/'config.json';path.write_text(json.dumps(value));path.chmod(0o600)
    return m.configuration(path),tmp_path


def event(path,session=fixtures.SESSION):
    return dict(hook_event_name='SessionStart',session_id=session,transcript_path=str(path/'native'/'first.jsonl'),cwd=str(path/'workspace'))


def test_exact_selection_registration_and_segment_rotation(selected):
    policy,path=selected;first=event(path)
    assert m.register(policy,first)['registered']
    assert m.register(policy,first)['reason']=='already_registered'
    assert not m.register(policy,dict(first,cwd=str(path)))['registered']
    assert not m.register(policy,dict(first,transcript_path=None))['registered']
    nested=path/'workspace'/'nested';nested.mkdir()
    assert m.register(policy,dict(first,cwd=str(nested)))['reason']=='already_registered'
    assert m.register(policy,dict(first,transcript_path=str(path/'native'/'second.jsonl')))['registered']
    jobs=[json.loads(p.read_text())['job']['jobs'][0] for p in (path/'registry').glob('*.json')]
    assert len(jobs)==2 and jobs[0]['session']==jobs[1]['session']
    assert jobs[0]['source_segment']!=jobs[1]['source_segment'] and all(x['context'] is None for x in jobs)
    for bad in (str(path/'outside.jsonl'),str(path/'native'/'..'/'outside.jsonl')):
        with pytest.raises(ValueError):m.register(policy,dict(first,transcript_path=bad))


def test_native_root_allows_existing_group_mode_but_not_world_writable(selected):
    policy,path=selected;config=path/'config.json';native=path/'native'
    native.chmod(0o775);assert m.configuration(config)==policy
    native.chmod(0o777)
    with pytest.raises(ValueError,match='native root'):m.configuration(config)


def test_interrupted_registration_is_idempotently_recovered(selected):
    policy,path=selected;e=event(path);job=m.job_for(policy,e);key=job['jobs'][0]['id'].removeprefix('desktop-')
    pending=path/'registry'/(key+'.pending');pending.write_bytes(m.intake.local('contract').encoded(dict(workspace=e['cwd'],job=job)));pending.chmod(0o600)
    assert m.register(policy,e)['reason']=='recovered_interrupted_registration'
    assert not pending.exists() and (path/'registry'/(key+'.json')).exists()


def test_hook_entry_registers_without_echoing_prompt(selected):
    policy,path=selected;e=dict(event(path),prompt='SYNTHETIC-PRIVATE-PROMPT')
    result=subprocess.run([sys.executable,str(ROOT/'desktop_capture.py'),'register','--config',str(path/'config.json')],
        input=json.dumps(e),text=True,capture_output=True,timeout=10)
    assert result.returncode==0 and json.loads(result.stdout)=={} and 'SYNTHETIC-PRIVATE-PROMPT' not in result.stderr
    for entry in (path/'registry').glob('*.json'):
        assert 'SYNTHETIC-PRIVATE-PROMPT' not in entry.read_text()


def test_changed_registry_policy_refused_before_collection(selected):
    policy,path=selected;m.register(policy,event(path));item=next((path/'registry').glob('*.json'))
    content=json.loads(item.read_text());content['job']['jobs'][0]['context']={'injected':'context'};item.write_text(json.dumps(content));item.chmod(0o600)
    with pytest.raises(Exception):m.run_once(policy,send=lambda _:None)


def test_workspace_revocation_stops_registered_source(selected):
    policy,path=selected;m.register(policy,event(path))
    other=path/'other';other.mkdir(mode=0o700);policy['workspaces']=[str(other)]
    result=m.run_once(policy,send=lambda _:None)
    assert result['sources']==0 and result['revoked_sources']==1 and result['passes']==[]


def test_cursor_fairness_and_restart_before_capture(selected,monkeypatch):
    policy,path=selected
    for x in range(4):m.register(policy,dict(event(path),transcript_path=str(path/'native'/f'{x}.jsonl')))
    seen=[]
    monkeypatch.setattr(m.capture_jobs,'run_once',lambda item,**kw:seen.append(item['jobs'][0]['source']))
    for _ in range(4):assert m.run_once(policy,send=lambda _:None,limit=1)['sources']==1
    assert len(set(seen))==4
    stale=path/'registry'/'.cursor.next';stale.write_text('partial');stale.chmod(0o600)
    assert m.run_once(policy,send=lambda _:None,limit=1)['sources']==1
    assert not stale.exists()


def test_synthetic_desktop_capture_outage_and_resume(selected,projects,evidence,reporting):
    if not os.environ.get('SHRR_SPECSTORY_FIXTURE_BINARY'):pytest.skip('reviewed collector required')
    policy,path=selected;source=path/'native'/'first.jsonl'
    source.write_text(''.join(json.dumps(row)+'\n' for row in fixtures.events(path/'workspace','legacy')));source.chmod(0o600)
    assert m.register(policy,event(path))['registered']
    def offline(_):raise OSError('synthetic outage')
    first=m.run_once(policy,send=offline);assert first['passes'][0]['delivery']['pending']>0
    second=m.run_once(policy,send=sender(reporting));assert second['passes'][0]['delivery']['pending']==0
    assert len([r for r,_ in events(reporting) if r['operation']=='artifact.record'])==1
    again=m.run_once(policy,send=sender(reporting));assert again['passes'][0]['delivery']['delivered']==0
