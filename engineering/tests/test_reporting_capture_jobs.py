"""Explicit jobs, private configuration, isolated collector faults and replay."""
import json
from pathlib import Path
import importlib.util
import pytest
from test_reporting_capture_intake import store,projects,evidence,reporting,sender

ROOT=Path(__file__).resolve().parents[1]/'tools/rras_reporting'
spec=importlib.util.spec_from_file_location('capture_jobs_test',ROOT/'capture_jobs.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def config(tmp_path):
    value=dict(contract='engineering-capture-jobs.v1',spool=str(tmp_path/'spool'),
        service_socket=str(tmp_path/'service.sock'),service_uid=995,
        jobs=[dict(id='selected',session='00000000-0000-4000-8000-000000000001',source=str(tmp_path/'selected.jsonl'),
            binary=str(tmp_path/'specstory'),scope=dict(kind='repository',id='jarvis'),context=None,
            authorization_reference='Synthetic fixture only')])
    path=tmp_path/'config.json';path.write_text(json.dumps(value));path.chmod(0o600);return path,value


def test_config_never_discovers_sources_or_starts_collector(tmp_path):
    path,value=config(tmp_path)
    assert m.configuration(path)==value
    assert not (tmp_path/'selected.jsonl').exists()
    path.chmod(0o644)
    with pytest.raises(ValueError):m.configuration(path)


@pytest.mark.parametrize('change',['extra','duplicate','relative','authorization','context'])
def test_invalid_jobs_fail_before_source_reads(tmp_path,change):
    path,value=config(tmp_path)
    if change=='extra':value['all_sessions']=True
    if change=='duplicate':value['jobs']*=2
    if change=='relative':value['jobs'][0]['source']='relative'
    if change=='authorization':value['jobs'][0]['authorization_reference']=''
    if change=='context':value['jobs'][0]['context']={}
    path.write_text(json.dumps(value))
    with pytest.raises(Exception):m.configuration(path)


def test_fault_status_is_private_deduplicated_and_flush_still_works(tmp_path,monkeypatch,projects,evidence,reporting):
    path,value=config(tmp_path);spool=m.intake.Spool(value['spool'],create=True)
    def fail(*a,**kw):raise OSError('SENSITIVE exception text must never reach the queue')
    monkeypatch.setattr(m.collectors,'collect_codex',fail)
    first=m.run_once(value,send=sender(reporting));again=m.run_once(value,send=sender(reporting))
    assert first['models_started']==0 and first['jobs'][0]['collection']=='gap'
    assert first['delivery']['pending']==0 and again['delivery']['delivered']==0
    for file in spool.root.rglob('*'):
        if file.is_file():assert b'SENSITIVE' not in file.read_bytes()


def test_v2_segment_jobs_keep_v1_exact_and_reject_duplicate_segment_identity(tmp_path):
    path,value=config(tmp_path)
    first=value['jobs'][0]
    first['source_segment']='first'
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError):m.configuration(path)
    value['contract']='engineering-capture-jobs.v2'
    second=dict(first,id='second',source=str(tmp_path/'second.jsonl'),source_segment='second')
    value['jobs'].append(second);path.write_text(json.dumps(value))
    assert m.configuration(path)==value
    second['source_segment']='first';path.write_text(json.dumps(value))
    with pytest.raises(ValueError,match='duplicate session segment'):m.configuration(path)
