import importlib.util
import json
from pathlib import Path
from unittest.mock import patch
import pytest

ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('installer',ROOT/'tools/rras_native/install_operator.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

@pytest.fixture
def installation(tmp_path):
    candidate=tmp_path/'candidate';candidate.mkdir();(candidate/'code.py').write_text('reviewed source\n')
    manifest=m.encoded({'files':{'code.py':m.digest((candidate/'code.py').read_bytes())}})
    (candidate/'manifest.json').write_bytes(manifest)
    layout={k:(str(tmp_path/k),u,g,mode) for k,u,g,mode in [('release',0,0,0o755),('control',0,0,0o700),('jobs',0,0,0o755),('workers',996,996,0o700)]}
    with patch.object(m,'CANDIDATE',candidate),patch.object(m,'MANIFEST',m.digest(manifest)),\
         patch.object(m,'LAYOUT',layout),patch.object(m,'JOURNAL',tmp_path/'journal'),\
         patch.object(m,'guards'),patch.object(m,'protected',side_effect=lambda p:Path(p)),patch.object(m.os,'chown'):
        yield tmp_path

def test_install_check_and_rollback_preserves_journal(installation):
    root=installation
    assert m.run('install')['success'];assert (root/'release/code.py').read_text()=='reviewed source\n'
    assert (root/'release/code.py').stat().st_mode&0o777==0o444
    assert m.run('check')['success']
    with pytest.raises(ValueError):m.run('install')
    assert m.run('rollback')['success']
    assert (root/'journal/rolled-back.json').exists() and not (root/'release').exists()

def test_preexisting_paths_never_adopted(installation):
    (installation/'workers').mkdir()
    with pytest.raises(ValueError):m.run('install')
    assert not (installation/'journal').exists()

def test_partial_install_resume_and_unknown_allocation_refusal(installation):
    original=m.allocate;count=0
    def fail(*row):
        nonlocal count
        if count==2:raise RuntimeError('simulated interruption')
        count+=1;original(*row)
    with patch.object(m,'allocate',side_effect=fail),pytest.raises(RuntimeError):m.run('install')
    assert m.run('resume')['success']

def test_created_without_inode_receipt_is_ambiguous(installation):
    original=m.write_record
    def fail(name,data):
        if name=='release.allocated.json':raise RuntimeError('lost receipt')
        return original(name,data)
    with patch.object(m,'write_record',side_effect=fail),pytest.raises(RuntimeError):m.run('install')
    for action in ('resume','rollback'):
        with pytest.raises(ValueError):m.run(action)
    assert (installation/'release').exists()

@pytest.mark.parametrize('change',['content','unexpected','runtime','inode'])
def test_rollback_checks_all_state_before_deletion(installation,change):
    m.run('install');root=installation
    if change=='content':(root/'release/code.py').chmod(0o600);(root/'release/code.py').write_text('changed')
    if change=='unexpected':(root/'release/extra').write_text('retain')
    if change=='runtime':(root/'control/approval.json').write_text('retain')
    if change=='inode':
        p=root/'jobs';p.rename(root/'old-jobs');p.mkdir()
    with pytest.raises(ValueError):m.run('rollback')
    assert (root/'release').exists() and (root/'workers').exists()

def test_interrupted_rollback_can_resume_without_reinstallation(installation):
    m.run('install');original=m.sync_dir
    def fail(path):
        if path==installation and not (installation/'workers').exists():raise RuntimeError('interrupted rollback')
        original(path)
    with patch.object(m,'sync_dir',side_effect=fail),pytest.raises(RuntimeError):m.run('rollback')
    with pytest.raises(ValueError):m.run('resume')
    assert m.run('rollback')['success']

def test_manifest_tampering_refused_before_allocation(installation):
    (installation/'candidate/code.py').write_text('changed')
    with pytest.raises(ValueError):m.run('install')
    assert not (installation/'journal').exists()

def test_inspection_is_read_only_and_allowed_while_slot_busy(installation):
    m.run('install')
    with patch.object(m.os,'geteuid',return_value=0),patch.object(m,'guards',side_effect=RuntimeError('busy')):
        result=m.run('inspect')
    assert result['host_changes'] is False and all(row['recorded'] for row in result['allocations'])

@pytest.mark.parametrize('bad',['slot','busy','timer_enabled','timer_query','timer_active'])
def test_host_guards_fail_closed(bad):
    from types import SimpleNamespace
    def command(args,**options):
        if args[0].endswith('pgrep'):return SimpleNamespace(returncode=0 if bad=='busy' else 1,stdout='')
        if 'is-enabled' in args:
            return SimpleNamespace(returncode=0 if bad in ('timer_enabled','timer_query') else 1,stdout='enabled' if bad=='timer_enabled' else 'disabled')
        field=args[args.index('-p')+1]
        value={'LoadState':'not-found','ActiveState':'inactive','SubState':'dead'}[field]
        if bad=='slot' and field=='LoadState':value='loaded'
        if bad=='timer_active' and field=='ActiveState':value='active'
        return SimpleNamespace(returncode=0,stdout=value)
    with patch.object(m.os,'geteuid',return_value=0),patch.object(m.subprocess,'run',side_effect=command):
        with pytest.raises(ValueError):m.guards()
