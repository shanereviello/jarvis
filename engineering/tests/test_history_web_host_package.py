"""Offline package tamper/bounds tests. Never stage or start root fixtures."""
import hashlib
import json
from pathlib import Path
import pytest
from test_history_web import web

package=web('host_package')


def fixture(tmp_path):
    candidate=tmp_path/'candidate';candidate.mkdir()
    files={name:b'synthetic source\n' for name in package.SOURCE_FILES}
    files['vendor/example.py']=b'pass\n'
    for name,raw in files.items():
        path=candidate/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    manifest={'contract':'engineering-history-web-host.v1','scope':'isolated-synthetic-only','source_commit':'a'*40,
        'files':{name:hashlib.sha256(raw).hexdigest() for name,raw in sorted(files.items())}}
    raw=package.encoded(manifest);(candidate/package.MANIFEST).write_bytes(raw)
    return candidate,hashlib.sha256(raw).hexdigest(),manifest


def test_exact_manifest_and_source_inventory(tmp_path):
    candidate,sha,manifest=fixture(tmp_path)
    actual,files=package.verify(candidate,sha)
    assert actual==manifest and set(files)==set(manifest['files'])


@pytest.mark.parametrize('name',['../escape','/absolute','vendor/../escape','vendor/a.pth','vendor/__pycache__/a.pyc','vendor/bin/uvicorn','engineering/unadmitted.py','vendor//bad'])
def test_unsafe_members_refused(name):
    with pytest.raises(ValueError):package.safe_name(name)


def test_tampered_member_refused(tmp_path):
    candidate,sha,_=fixture(tmp_path);(candidate/'vendor/example.py').write_bytes(b'changed')
    with pytest.raises(ValueError):package.verify(candidate,sha)


def test_symlink_member_refused(tmp_path):
    candidate,sha,_=fixture(tmp_path);path=candidate/'vendor/example.py';path.unlink();path.symlink_to(tmp_path/'other')
    with pytest.raises((ValueError,FileNotFoundError)):package.verify(candidate,sha)


def test_changed_manifest_hash_refused(tmp_path):
    candidate,sha,_=fixture(tmp_path)
    with pytest.raises(ValueError):package.verify(candidate,'0'*64)


def test_missing_required_source_refused_even_with_new_hash(tmp_path):
    candidate,sha,manifest=fixture(tmp_path);manifest['files'].pop(next(iter(package.SOURCE_FILES)))
    raw=package.encoded(manifest);(candidate/package.MANIFEST).write_bytes(raw)
    with pytest.raises(ValueError):package.verify(candidate,hashlib.sha256(raw).hexdigest())


def test_duplicate_json_and_nonfinite_refused():
    for raw in (b'{"a":1,"a":2}',b'{"a":NaN}'):
        with pytest.raises(ValueError):package.decode(raw)


def test_helper_is_pinned_stdlib_bootstrap(tmp_path):
    path=tmp_path/'stage.py';sha=package.emit_helper(path)
    assert hashlib.sha256(path.read_bytes()).hexdigest()==sha
    text=path.read_text();compile(text,str(path),'exec')
    assert 'explicit sudo acceptance required' in text and 'preserve existing fixture; no automatic retry' in text
    assert 'import jwt' not in text and 'import uvicorn' not in text
    assert 'isolated_dashboard_v02_host_verified' in text
    assert 'rras-history-web-acceptance-v02-20261107' in text


def test_host_driver_preserves_unit_guards_and_isolation():
    driver=web('host_driver');properties=driver.web_properties()
    assert 'User=61175' in properties and 'Group=61175' in properties
    assert 'CapabilityBoundingSet=' in properties and 'NoNewPrivileges=yes' in properties
    assert 'PrivateNetwork=yes' in properties and 'RuntimeMaxSec=180' in properties
    assert any(p.startswith('InaccessiblePaths=') and str(driver.STATE/'history') in p for p in properties)
    assert not any(p.startswith('ExecStart=') for p in properties)


def test_fixture_probe_is_not_a_production_role():
    probe=web('host_probe')
    with pytest.raises(ValueError):probe.seed()
    with pytest.raises(ValueError):probe.serve()


def test_temporary_identities_are_locked_without_home_and_verified(monkeypatch):
    driver=web('host_driver');calls=[];verified=[]
    monkeypatch.setattr(driver,'identity_command',lambda argv:calls.append(argv))
    monkeypatch.setattr(driver,'verify_identity',lambda uid:verified.append(uid))
    driver.create_identities()
    assert verified==[driver.OWNER,driver.READER]
    users=[argv for argv in calls if argv[0]=='/usr/sbin/useradd']
    assert len(users)==2
    for argv in users:
        assert '--no-create-home' in argv and '--no-user-group' in argv and '--no-log-init' in argv
        assert argv[argv.index('--password')+1]=='!'
        assert argv[argv.index('--shell')+1]=='/usr/sbin/nologin'
        assert argv[argv.index('--home-dir')+1]=='/nonexistent'


def test_identity_verification_refuses_extra_group(monkeypatch):
    import types
    driver=web('host_driver');uid=driver.OWNER;name=driver.ACCOUNTS[uid]
    user=types.SimpleNamespace(pw_uid=uid,pw_gid=uid,pw_dir='/nonexistent',pw_shell='/usr/sbin/nologin',pw_name=name)
    group=types.SimpleNamespace(gr_gid=uid,gr_mem=[])
    monkeypatch.setattr(driver.pwd,'getpwnam',lambda value:user)
    monkeypatch.setattr(driver.pwd,'getpwuid',lambda value:user)
    monkeypatch.setattr(driver.pwd,'getpwall',lambda:[user])
    monkeypatch.setattr(driver.grp,'getgrnam',lambda value:group)
    monkeypatch.setattr(driver.os,'getgrouplist',lambda name,uid:[uid,995])
    with pytest.raises(ValueError):driver.verify_identity(uid)
