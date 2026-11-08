"""Registered jobs rotate fairly and cannot expand the installed source policy."""
import json
import pytest
from test_reporting_runtime_reporting import setup,m,projects,store,reporting
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
