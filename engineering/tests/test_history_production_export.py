"""Pinned export-only tooling; disposable source snapshots and publication order."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
import pytest
from test_engineering_history_local import module
from test_history_managed_link import setup,exporter

package=module('managed_export_package');entry=module('managed_export_entry')
SOURCE=Path(__file__).resolve().parents[2]


def plan_for(packet):
    work=packet['work']
    return {'contract':'engineering-production-export.v1','scope':'one-work-revision-allowlisted-export-only','capture_id':'1'*32,
            'journal_id':packet['journal_id'],'work_item_id':work['work_item_id'],'repository_id':work['repository_id'],
            'source_work_sha256':work['record_sha256'],'baseline':work['baseline'],'allowed_paths':work['requested_paths'],'reader_uid':1000}


@pytest.fixture
def candidate(tmp_path):
    vendor=tmp_path/'vendor';vendor.mkdir();(vendor/'fixture.py').write_text('SYNTHETIC=True\n')
    root=tmp_path/'candidate';result=package.build(SOURCE,vendor,root,'a'*40)
    return root,result


@pytest.fixture
def tool(tmp_path):
    helper=tmp_path/'tool.py';package.emit_helper(helper)
    spec=importlib.util.spec_from_file_location('generated_export_tool',helper)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def test_generated_tool_pins_production_subset_and_excludes_fixture_code(candidate,tool):
    root,result=candidate;_,files=tool.verify(root,result['manifest_sha256'])
    assert not any('host_' in name or 'examples/' in name for name in files)
    assert files['engineering/tools/rras_native/engineering_export.py']==(SOURCE/'engineering/tools/rras_native/engineering_export.py').read_bytes()


@pytest.mark.parametrize('change',['reader','scope','source','capture','extra','paths'])
def test_export_plan_cannot_select_arbitrary_reader_source_or_scope(setup,change):
    plan=plan_for(setup[2])
    if change=='reader':plan['reader_uid']=0
    if change=='scope':plan['scope']='execute'
    if change=='source':plan['source_root']='/etc'
    if change=='capture':plan['capture_id']='../root'
    if change=='extra':plan['approval']=True
    if change=='paths':plan['allowed_paths']=['../secret']
    with pytest.raises(ValueError):package.validate_plan(plan)


def test_producer_uses_one_snapshot_for_all_pages(setup,tmp_path,monkeypatch):
    journal,_,packet,_,_=setup;plan=plan_for(packet);out=tmp_path/'out';out.mkdir(mode=0o700)
    original=exporter.read_snapshot;reads=[]
    def snapshot(root):reads.append(root);return original(root)
    monkeypatch.setattr(exporter,'read_snapshot',snapshot);monkeypatch.setattr(entry,'native',lambda:exporter)
    before=journal.path.read_bytes();answer=entry.produce(journal.root,out,plan)
    assert reads==[journal.root] and answer['events']==1
    assert journal.path.read_bytes()==before
    manifest=json.loads((out/'export-result.json').read_bytes())
    assert manifest['work']['record_sha256']==plan['source_work_sha256']
    raw=(out/'packet-000.json').read_bytes();assert hashlib.sha256(raw).hexdigest()==manifest['packets'][0]['sha256']


@pytest.mark.parametrize('field',['work_item_id','repository_id','baseline','allowed_paths'])
def test_producer_refuses_changed_reviewed_binding(setup,tmp_path,monkeypatch,field):
    journal,_,packet,_,_=setup;plan=plan_for(packet);out=tmp_path/'out';out.mkdir(mode=0o700)
    plan[field]={'work_item_id':'wrk_'+'f'*32,'repository_id':'other','baseline':None,'allowed_paths':['other.py']}[field]
    monkeypatch.setattr(entry,'native',lambda:exporter)
    with pytest.raises(ValueError,match='reviewed source'):entry.produce(journal.root,out,plan)
    assert not (out/'export-result.json').exists() and not list(out.glob('packet-*.json'))


def test_preflight_only_creates_nothing(tool,tmp_path,monkeypatch):
    journal=tmp_path/'never-created'
    monkeypatch.setattr(tool,'preflight',lambda *_:({}, {}, {}, b'', tmp_path, journal, tmp_path/'handoff'))
    answer=tool.stage(tmp_path,'a'*64,tmp_path/'plan','b'*64,check_only=True)
    assert answer['mutations'] is False and not journal.exists()


def test_export_reader_cannot_have_network_caps_groups_or_import_route(tool,tmp_path):
    command=tool.export_command(tmp_path,tmp_path/'journal')
    assert command[command.index('--reuid')+1]=='0'
    for flag in ('--net','--clear-groups','--no-new-privs','--bounding-set=-all','--inh-caps=-all','--ambient-caps=-all'):assert flag in command
    assert 'managed_export_entry.py' in command[-2] and not any('deliver' in arg for arg in command)


def test_handoff_is_filled_before_directory_owner_transfer(candidate,tool,setup,tmp_path,monkeypatch):
    root,result=candidate;manifest,files=tool.verify(root,result['manifest_sha256'])
    journal_source,_,packet,_,_=setup;plan=plan_for(packet)
    journals=tmp_path/'journals';handoffs=tmp_path/'handoffs';journal=journals/'capture';handoff=handoffs/'capture';release=tmp_path/'release'
    monkeypatch.setattr(tool,'JOURNALS',journals);monkeypatch.setattr(tool,'HANDOFFS',handoffs)
    monkeypatch.setattr(tool,'preflight',lambda *_:(manifest,files,plan,package.encoded(plan),release,journal,handoff))
    monkeypatch.setattr(entry,'native',lambda:exporter)
    def reader(*args,**kwargs):
        value=entry.produce(journal_source.root,journal,plan)
        return SimpleNamespace(returncode=0,stdout=package.encoded(value),stderr=b'')
    monkeypatch.setattr(tool.subprocess,'run',reader);monkeypatch.setattr(tool.os,'fchown',lambda *_:None)
    transfers=[]
    def transfer(path,uid,gid):
        assert path==handoff and uid==gid==1000
        assert (handoff/'export-result.json').exists() and (handoff/'packet-000.json').exists() and (handoff/'plan.json').exists()
        transfers.append(str(path))
    monkeypatch.setattr(tool.os,'chown',transfer)
    answer=tool.stage(root,result['manifest_sha256'],tmp_path/'plan','b'*64)
    assert len(transfers)==1 and answer['history_records_written'] is False and answer['services_changed'] is False
    assert (handoff/'packet-000.json').read_bytes()==(journal/'packet-000.json').read_bytes()
    assert (journal/'complete.json').exists()


def test_unprivileged_preflight_refused(tool,tmp_path,monkeypatch):
    monkeypatch.setattr(tool.os,'getuid',lambda:1000)
    with pytest.raises(ValueError,match='administrator'):tool.preflight(tmp_path,'a'*64,tmp_path/'plan','b'*64)
