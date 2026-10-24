"""Offline packaging/controller/role logic; actual distinct UIDs require sudo."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
import pytest
from test_engineering_history_local import module

package=module('managed_host_package');driver=module('managed_host_driver');probe=module('managed_host_probe')
SOURCE=Path(__file__).resolve().parents[2]


@pytest.fixture
def candidate(tmp_path):
    vendor=tmp_path/'vendor';vendor.mkdir();(vendor/'synthetic.py').write_text('SYNTHETIC=True\n')
    dest=tmp_path/'candidate';result=package.build(SOURCE,vendor,dest,'a'*40)
    return dest,result


def test_manifest_pins_bridge_native_history_and_fixture(candidate):
    dest,result=candidate;manifest,files=package.verify(dest,result['manifest_sha256'])
    for name in ('engineering/tools/rras_native/engineering_export.py','engineering/tools/rras_history/link_delivery.py',
                 'engineering/contracts/engineering-managed-export-v1.schema.json'):
        assert files[name]==(SOURCE/name).read_bytes()
    assert manifest['scope']=='isolated-synthetic-only' and result['root_mutations'] is False


@pytest.mark.parametrize('name',['../x','vendor/../x','/etc/passwd','vendor/evil.pth','vendor/.git/config','vendor//x','unlisted.py'])
def test_unsafe_payload_path_refused(name):
    with pytest.raises(ValueError):package.safe_name(name)


@pytest.mark.parametrize('change',['source','symlink','hardlink','scope'])
def test_changed_payload_cannot_stage(candidate,change):
    dest,result=candidate;target=dest/'engineering/tools/rras_history/managed_host_probe.py'
    if change=='source':target.write_text('changed')
    if change=='symlink':target.unlink();target.symlink_to(dest/'managed-host-manifest.json')
    if change=='hardlink':os.link(target,dest/'other')
    if change=='scope':
        p=dest/'managed-host-manifest.json';m=json.loads(p.read_bytes());m['scope']='production';p.write_bytes(package.encoded(m));result['manifest_sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
    with pytest.raises(ValueError):package.verify(dest,result['manifest_sha256'])


@pytest.mark.parametrize('role,uid',[('seed',0),('export',0),('init',61101),('service',61101),('resume',61102),('denial',61103),('denial',996)])
def test_commands_scope_numeric_roles_network_caps_and_groups(role,uid):
    argv=driver.command(role,uid)
    assert argv[argv.index('--reuid')+1]==str(uid) and argv[argv.index('--regid')+1]==str(uid)
    for flag in ('--net','--clear-groups','--pdeathsig=TERM','--no-new-privs','--bounding-set=-all','--inh-caps=-all','--ambient-caps=-all'):assert flag in argv
    assert '--groups' not in argv


@pytest.mark.parametrize('role,uid',[('seed',61102),('resume',0),('denial',0),('execute',61102)])
def test_role_escalation_or_unknown_role_refused(role,uid):
    with pytest.raises(ValueError):driver.command(role,uid)


def test_generated_bootstrap_guard_and_probe_share_one_state(tmp_path,monkeypatch):
    helper=tmp_path/'helper.py';sha=package.emit_helper(helper)
    assert hashlib.sha256(helper.read_bytes()).hexdigest()==sha
    spec=importlib.util.spec_from_file_location('generated_managed_bootstrap',helper)
    tool=importlib.util.module_from_spec(spec);spec.loader.exec_module(tool)
    assert tool.STATE==driver.STATE==probe.STATE==package.STATE
    monkeypatch.setattr(tool.os,'getuid',lambda:0);monkeypatch.setattr(tool.os,'geteuid',lambda:0)
    monkeypatch.setattr(tool,'protected',lambda _:None)
    original=tool.Path.exists
    monkeypatch.setattr(tool.Path,'exists',lambda path:True if path==tool.STATE else original(path))
    monkeypatch.setattr(tool,'verify',lambda *_:pytest.fail('existing fixture must refuse before verification or mutation'))
    with pytest.raises(ValueError,match='preserve existing'):tool.stage(tmp_path,'a'*64)


def test_private_file_denial_does_not_count_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):probe.denied(tmp_path/'absent')


def test_fixture_role_logic_seeds_exports_and_replays_real_sqlite(tmp_path,monkeypatch):
    # Simulate only UID checks; all SQLite is disposable under the actual caller.
    # This deliberately does not claim network/permission/cross-UID acceptance.
    state=tmp_path/'fixture';state.mkdir(mode=0o700)
    for name in ('source','export','client','client/input','history','runtime'):(state/name).mkdir(mode=0o700)
    monkeypatch.setattr(probe,'STATE',state)
    monkeypatch.setattr(probe,'os',SimpleNamespace(getuid=lambda:0,fchmod=os.fchmod,fsync=os.fsync))
    assert probe.seed()['records']==5
    before=(state/'source/workflow.sqlite3').read_bytes();assert probe.exported()['pages']==2
    assert (state/'source/workflow.sqlite3').read_bytes()==before
    for name in ('work','first','second'):
        target=state/'client/input'/(name+'.json');target.write_bytes((state/'export'/(name+'.json')).read_bytes());target.chmod(0o600)
    monkeypatch.setattr(probe,'os',os);monkeypatch.setattr(probe,'CLIENT',os.getuid());monkeypatch.setattr(probe,'SERVICE',os.getuid())
    history=module('store').Store(state/'history',create=True)
    def call(message):
        if message['method']=='submit':return history.submit(message['request'],peer_uid=os.getuid())
        if message['method']=='history':return history.history()
        pytest.fail('unexpected fixture method')
    monkeypatch.setattr(probe,'call',call)
    assert probe.client('lost-response')['cursor_advanced'] is False
    assert probe.client('resume')['next_after']==2
    assert probe.client('replay')['history_records']==3


def test_controller_never_uses_accounts_systemd_or_production_paths():
    import ast
    tree=ast.parse((SOURCE/'engineering/tools/rras_history/managed_host_driver.py').read_text())
    strings=[node.value for node in ast.walk(tree) if isinstance(node,ast.Constant) and isinstance(node.value,str)]
    assert not any('/usr/bin/systemctl' in value or '/usr/sbin/useradd' in value or '/var/lib/rras-workflow' in value for value in strings)
