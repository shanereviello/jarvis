"""Offline fixture bindings/custody; real hardened-unit execution requires sudo."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest
from test_engineering_history_local import module

p=module('unit_acceptance_package');runtime=module('production_package');u=module('unit_acceptance')
SOURCE=Path(__file__).resolve().parents[2]


@pytest.fixture
def candidate(tmp_path):
    vendor=tmp_path/'vendor';vendor.mkdir();(vendor/'fixture.py').write_text('SYNTHETIC=True\n')
    root=tmp_path/'candidate';result=p.build(SOURCE,vendor,root,'a'*40)
    return root,result


def test_nested_runtime_and_all_tooling_are_pinned(candidate):
    root,result=candidate
    manifest,files=p.verify(root,result['manifest_sha256'])
    runtime_manifest,_=runtime.verify(root,manifest['runtime_manifest_sha256'])
    assert not runtime_manifest['activation_authorized']
    assert files['engineering/tools/rras_history/production_entry.py']==(SOURCE/'engineering/tools/rras_history/production_entry.py').read_bytes()
    assert result['host_mutations'] is False
    assert 'engineering/tools/rras_history/unit_acceptance.py' in files


def test_fixture_changes_only_scoped_identity_paths_and_extra_safety_bounds(candidate):
    root,_=candidate;original=(root/'deployment/rras-engineering-history.service').read_bytes()
    text=u.fixture_unit(original,root).decode()
    assert 'User=rras-hist-fixture3\n' in text and 'Group=rras-hist-fixture3\nSupplementaryGroups=\n' in text
    assert 'RuntimeDirectory='+u.NAME+'\n' in text
    assert str(u.STATE/'private') in text and str(u.RUNTIME/'service.sock') in text
    assert '[Install]' not in text and 'WantedBy=' not in text
    assert 'TimeoutStartSec=25s' in text and 'RuntimeMaxSec=180s' in text
    ignored=('User=','Group=','WorkingDirectory=','ExecStart=','RuntimeDirectory=','ReadWritePaths=','ConditionPathExists=')
    for line in original.decode().splitlines():
        if not line or line.startswith(ignored) or line in ('[Install]','WantedBy=multi-user.target'):continue
        assert line in text
    assert 'ExecStartPost=' in text and 'unit-check' in text


@pytest.mark.parametrize('name',['/etc/x','../x','vendor/../x','vendor//x','vendor/.git/config','vendor/evil.pth','not-reviewed.py'])
def test_payload_path_refusals(name):
    with pytest.raises(ValueError):p.safe_name(name)


@pytest.mark.parametrize('kind',['source','runtime','scope','symlink','hardlink'])
def test_mutated_or_unsafe_payload_cannot_stage(candidate,kind):
    root,result=candidate;manifest_path=root/'unit-acceptance-manifest.json';manifest=json.loads(manifest_path.read_bytes())
    target=root/'engineering/tools/rras_history/unit_acceptance_probe.py'
    if kind=='source':target.write_text('changed')
    if kind=='runtime':(root/'runtime-manifest.json').write_text('{}')
    if kind=='scope':manifest['scope']='production-activation'
    if kind=='symlink':target.unlink();target.symlink_to(root/'runtime-manifest.json')
    if kind=='hardlink':os.link(target,root/'second-link')
    raw=p.encoded(manifest);manifest_path.write_bytes(raw)
    with pytest.raises(ValueError):p.verify(root,hashlib.sha256(raw).hexdigest())


def test_standalone_root_helper_refuses_without_sudo(tmp_path):
    helper=tmp_path/'helper.py';digest=p.emit_helper(helper)
    assert hashlib.sha256(helper.read_bytes()).hexdigest()==digest
    result=subprocess.run([sys.executable,'-I','-B',str(helper),'--candidate',str(tmp_path),'--manifest-sha256','a'*64],capture_output=True)
    assert result.returncode==1 and not result.stdout and b'preserve fixture evidence' in result.stderr
    assert 'from jsonschema' not in helper.read_text()


@pytest.mark.parametrize('action',['restart','enable','disable','rm','daemon-reload'])
def test_control_api_can_only_start_stop_its_fixed_fixture_unit(action):
    with pytest.raises(ValueError):u.control(action)


def test_private_groups_and_fixed_unit_scope():
    for uid in (61091,61092,61093,1000,996):
        command=u.child_command('rpc',uid)
        assert command[command.index('--regid')+1]==str(uid) and '--clear-groups' in command
        assert '--groups' not in command and '--net' in command
    assert u.control('start')==['/usr/bin/systemctl','start','rras-history-unit-acceptance-attempt03-20261023.service']
    assert u.control('stop')[-1]==u.UNIT
    with pytest.raises(ValueError):u.child_command('rpc',0)


def test_refuse_rebuild_over_existing_candidate(candidate):
    root,_=candidate
    with pytest.raises(FileExistsError):p.build(SOURCE,root/'vendor',root,'a'*40)


def test_private_file_denial_does_not_treat_missing_fixture_as_permission_proof(tmp_path):
    probe=module('unit_acceptance_probe')
    path=tmp_path/'absent'
    with pytest.raises(FileNotFoundError):probe.denied(path,os.O_RDONLY)
    probe.denied(path,os.O_RDONLY,missing_allowed=True)


def test_denial_probe_never_writes_an_unexpectedly_accessible_file(tmp_path):
    probe=module('unit_acceptance_probe');path=tmp_path/'synthetic';path.write_text('preserve')
    with pytest.raises(ValueError,match='unexpectedly allowed'):probe.denied(path,os.O_WRONLY)
    assert path.read_text()=='preserve'



def test_fixture_identity_is_locked_no_home_and_exactly_scoped():
    command=u.user_create_command()
    assert command[0]=='/usr/sbin/useradd' and command[-1]=='rras-hist-fixture3'
    assert command[command.index('--uid')+1]=='61091'
    assert command[command.index('--password')+1]=='!'
    assert command[command.index('--shell')+1]=='/usr/sbin/nologin'
    assert '--no-create-home' in command and '--no-log-init' in command
    assert '-K' not in command
    assert u.group_create_command()==['/usr/sbin/groupadd','--gid','61091','rras-hist-fixture3']


def test_fixture_identity_collision_is_refused(monkeypatch):
    monkeypatch.setattr(u.pwd,'getpwnam',lambda _:object())
    with pytest.raises(ValueError,match='already allocated'):u.require_identity_absent()


@pytest.mark.parametrize('change',['uid','group','home','shell','member'])
def test_identity_cleanup_guard_refuses_unrelated_or_changed_account(monkeypatch,change):
    from types import SimpleNamespace
    user=SimpleNamespace(pw_uid=61091,pw_gid=61091,pw_dir='/nonexistent',pw_shell='/usr/sbin/nologin',pw_name=u.ACCOUNT)
    group=SimpleNamespace(gr_gid=61091,gr_mem=[])
    if change=='uid':user.pw_uid=1000
    if change=='group':group.gr_gid=1000
    if change=='home':user.pw_dir='/home/unrelated'
    if change=='shell':user.pw_shell='/bin/bash'
    if change=='member':group.gr_mem=['unrelated']
    monkeypatch.setattr(u.pwd,'getpwnam',lambda _:user)
    monkeypatch.setattr(u.grp,'getgrnam',lambda _:group)
    monkeypatch.setattr(u.pwd,'getpwall',lambda:[user])
    with pytest.raises(ValueError,match='association changed'):u.verify_identity()


def test_new_attempt_refuses_allocated_numeric_group(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(u.pwd,'getpwall',lambda:[])
    monkeypatch.setattr(u.grp,'getgrall',lambda:[SimpleNamespace(gr_gid=u.SERVICE)])
    with pytest.raises(ValueError,match='already allocated'):u.require_ids_unused()


def test_new_attempt_does_not_adopt_retained_old_group(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(u.pwd,'getpwall',lambda:[])
    monkeypatch.setattr(u.grp,'getgrall',lambda:[SimpleNamespace(gr_gid=61081)])
    monkeypatch.setattr(u.Path,'glob',lambda *_:[])
    u.require_ids_unused()
    assert u.SERVICE==61091 and u.ACCOUNT=='rras-hist-fixture3'
