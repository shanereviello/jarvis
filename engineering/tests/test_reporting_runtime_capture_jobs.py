"""Registered jobs rotate fairly and cannot expand the installed source policy."""
import json
import os
import copy
from pathlib import Path
import pytest
from test_reporting_runtime_reporting import setup,m,projects,store,reporting
from test_reporting_capture_intake import evidence
from test_reporting_codex_runtime import uid


def registered(tmp_path,projects,count):
    policy,config,spool,_,request=setup(tmp_path,projects)
    native=tmp_path/'native';native.mkdir(mode=0o700);jobs=tmp_path/'jobs';jobs.mkdir(mode=0o700)
    config['capture']=dict(binary=str(tmp_path/'specstory'),native_root=str(native),jobs=str(jobs),
        authorization_reference='Synthetic selected runtime test',service_socket=str(tmp_path/'service.sock'),service_uid=995)
    reporter=m.Reporter(config,policy)
    for number in range(count):reporter.register_capture(dict(session=uid(10+number),thread=uid(100+number),issue=uid(3)),dict(path=str(native/(str(number)+'.jsonl'))))
    return reporter,jobs


def test_rotation_visits_every_registered_source_without_native_discovery(tmp_path,projects,reporting):
    reporter,jobs=registered(tmp_path,projects,5);runner=m.local('runtime_capture_jobs')
    first=runner.selected(reporter,2);second=runner.selected(reporter,2);third=runner.selected(reporter,2)
    sources=[x['jobs'][0]['source'] for x in first+second+third]
    assert len(sources)==6 and len(set(sources))==5
    assert list((tmp_path/'native').iterdir())==[]
    assert (jobs/'.cursor.json').stat().st_mode & 0o777==0o600


def test_registered_sources_remain_selectable_with_issue_scoped_v2_policy(tmp_path,projects,reporting):
    original,jobs=registered(tmp_path,projects,1)
    policy=copy.deepcopy(original.policy)
    policy.update(contract='codex-runtime-policy.v2',
        workspaces={uid(3):str(tmp_path/'issue-workspace')},
        native_sockets={uid(3):str(tmp_path/('coding-'+uid(3)+'.sock'))})
    runtime=m.local('codex_runtime')
    reporter=m.Reporter(original.configuration,runtime.policy(policy))
    selected=m.local('runtime_capture_jobs').selected(reporter,1)
    assert len(selected)==1
    assert selected[0]['jobs'][0]['context']==original.configuration['contexts'][uid(3)]
    assert len(list(jobs.glob('*.json')))==2  # registered job and retained cursor


@pytest.mark.parametrize('field',['source','binary','context','service_socket','authorization_reference'])
def test_registered_entry_cannot_change_installed_capture_authority(tmp_path,projects,reporting,field):
    reporter,jobs=registered(tmp_path,projects,1);path=next(jobs.glob('*.json'));value=json.loads(path.read_text())
    if field=='service_socket':value[field]=str(tmp_path/'other.sock')
    elif field=='context':value['jobs'][0][field]=None
    elif field=='authorization_reference':value['jobs'][0][field]='Different authorization'
    else:value['jobs'][0][field]=str(tmp_path/'unrelated-private')
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError):m.local('runtime_capture_jobs').selected(reporter)


def test_capacity_stops_registration_without_removing_sources_or_jobs(tmp_path,projects,reporting,monkeypatch):
    reporter,jobs=registered(tmp_path,projects,1)
    # A foreign entry is a stop/report condition, never an invitation to delete it.
    foreign=jobs/'unexpected.json';foreign.write_text('{}');foreign.chmod(0o600)
    before={x.name:x.read_bytes() for x in jobs.iterdir()}
    with pytest.raises(ValueError):reporter.register_capture(dict(session=uid(44),thread=uid(45),issue=uid(3)),dict(path=str(tmp_path/'native/new.jsonl')))
    with pytest.raises(ValueError):m.local('runtime_capture_jobs').selected(reporter)
    assert before=={x.name:x.read_bytes() for x in jobs.iterdir()}


def test_recover_fsynced_cursor_after_interrupted_rotation(tmp_path,projects,reporting):
    reporter,jobs=registered(tmp_path,projects,3);runner=m.local('runtime_capture_jobs')
    names=sorted(path.name for path in jobs.glob('*.json'))
    pending=jobs/'.cursor.next';pending.write_bytes(reporter.c.encoded({'after':names[0]}));pending.chmod(0o600)
    selected=runner.selected(reporter,1)
    assert len(selected)==1
    assert not pending.exists()
    assert reporter.c.decode((jobs/'.cursor.json').read_bytes())=={'after':names[1]}
    assert len(runner.selected(reporter,3))==3


def test_corrupt_interrupted_cursor_refuses_without_deleting_it(tmp_path,projects,reporting):
    reporter,jobs=registered(tmp_path,projects,1);runner=m.local('runtime_capture_jobs')
    pending=jobs/'.cursor.next';pending.write_text('{"after":"invalid"}');pending.chmod(0o600)
    with pytest.raises(ValueError,match='exact registry cursor'):
        runner.selected(reporter)
    assert pending.exists()


def test_registered_actual_collector_outage_and_growth_recovery(tmp_path,projects,evidence,reporting):
    from test_reporting_capture_intake import sender,events
    from test_reporting_capture_collectors import fixtures
    binary=os.environ.get('SHRR_SPECSTORY_FIXTURE_BINARY')
    if not binary:pytest.skip('opt-in pinned synthetic collector required')
    policy,config,spool,_,_=setup(tmp_path,projects)
    native=tmp_path/'native';native.mkdir(mode=0o700)
    jobs=tmp_path/'jobs';jobs.mkdir(mode=0o700)
    config['capture']=dict(binary=str(Path(binary).resolve()),native_root=str(native),jobs=str(jobs),
        authorization_reference='Synthetic registered collection only',service_socket=str(tmp_path/'service.sock'),service_uid=995)
    reporter=m.Reporter(config,policy);source=native/'selected.jsonl';repo=tmp_path/'worker';repo.mkdir()
    source.write_text(''.join(json.dumps(row)+'\n' for row in fixtures.events(repo,'legacy')));source.chmod(0o600)
    reporter.register_capture(dict(session=uid(10),thread=fixtures.SESSION,issue=uid(3)),dict(path=str(source)))
    runner=m.local('runtime_capture_jobs')
    def offline(_):raise OSError('synthetic history outage')
    first=runner.run_once(reporter,send=offline)
    assert first['sources']==1 and first['passes'][0]['jobs'][0]['collection']=='changed'
    assert first['passes'][0]['delivery']['pending']>0
    second=runner.run_once(reporter,send=sender(reporting))
    assert second['passes'][0]['jobs'][0]['collection']=='unchanged'
    assert second['passes'][0]['delivery']['pending']==0
    with source.open('a') as stream:
        stream.write(json.dumps(dict(type='event_msg',timestamp='2026-11-07T12:00:05Z',
            payload=dict(type='user_message',message='Synthetic later message'))) + '\n')
    third=runner.run_once(reporter,send=sender(reporting))
    assert third['passes'][0]['jobs'][0]['collection']=='changed'
    assert third['passes'][0]['delivery']['pending']==0
    artifacts=[request for request,_ in events(reporting) if request['operation']=='artifact.record']
    assert [item['body']['version'] for item in artifacts]==[1,2]
    assert artifacts[0]['context']==artifacts[1]['context']==config['contexts'][uid(3)]
    assert runner.run_once(reporter,send=sender(reporting))['passes'][0]['jobs'][0]['collection']=='unchanged'
