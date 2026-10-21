"""Native heartbeat predicate and distinction from lifecycle/drain freshness."""
from datetime import datetime,timezone
import importlib.util
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]/'tools/rras_native'

def checker():
    spec=importlib.util.spec_from_file_location('activation',ROOT/'activate_workflow_upgrade.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    namespace={};exec(m.HEARTBEAT_CHECK,namespace);return namespace['heartbeat_live']

def heartbeat():return {'pid':168,'start_time':1004.0,'monotonic':5990.0,'updated_at':datetime.fromtimestamp(1090,timezone.utc).isoformat()}

def test_recent_heartbeat_binds_to_same_process_birth():
    assert checker()(heartbeat(),168,1000.0,1100.0,6000.0)

@pytest.mark.parametrize('field,value',[('pid',169),('pid',True),('start_time',999.0),('start_time',1101.0),('start_time',True),
    ('start_time',float('nan')),('monotonic',5909.0),('monotonic',6001.0),('monotonic',float('inf')),('monotonic',True),
    ('updated_at','1970-01-01T00:16:00+00:00'),('updated_at','1970-01-01T00:19:00+00:00'),('updated_at','1970-01-01T00:18:10'),('updated_at','invalid')])
def test_stale_foreign_or_malformed_heartbeat_refuses(field,value):
    h=heartbeat();h[field]=value;assert not checker()(h,168,1000.0,1100.0,6000.0)

@pytest.mark.parametrize('missing',['pid','start_time','monotonic','updated_at'])
def test_missing_heartbeat_field_refuses(missing):
    h=heartbeat();del h[missing];assert not checker()(h,168,1000.0,1100.0,6000.0)


def test_previous_process_heartbeat_cannot_vouch_for_reused_pid():
    assert not checker()(heartbeat(),168,1005.0,1100.0,6000.0)
