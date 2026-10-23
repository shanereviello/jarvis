"""Real user-owned ACLs and inactive package checks; no production installation."""
import copy
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
from unittest.mock import patch

import pytest
from test_engineering_history_local import module,request
from test_engineering_history_unix import env

p=module('production_package');entry=module('production_entry');u=module('unix');c=module('contract')
SOURCE=Path(__file__).resolve().parents[2]


def acl(path):
    return subprocess.check_output(['/usr/bin/getfacl','--numeric','--omit-header',str(path)],text=True)


@pytest.fixture
def package(tmp_path):
    vendor=tmp_path/'vendor';vendor.mkdir();(vendor/'synthetic.py').write_text('SYNTHETIC=True\n')
    destination=tmp_path/'candidate';result=p.build(SOURCE,vendor,destination,'a'*40)
    return destination,result


def test_package_is_deterministic_and_inactive(package,tmp_path):
    destination,result=package
    manifest,files=p.verify(destination,result['manifest_sha256'])
    assert result['host_mutations'] is False and manifest['activation_authorized'] is False
    assert manifest['stage_authorized'] is False
    plan=json.loads(files['deployment/install-plan.json'])
    assert not plan['change_existing_user_groups'] and plan['initial_data']=='empty-only-no-synthetic-fixture-import'
    assert 'encrypted-backup-and-restore-acceptance' in plan['gates']
    assert p.build(SOURCE,tmp_path/'vendor',tmp_path/'other','a'*40)==result
    assert not any(name.endswith(('host_probe.py','host_acceptance.py')) for name in files)


def test_payload_identity_excludes_artifacts_but_verify_pins_them(package):
    destination,result=package
    manifest,files=p.verify(destination,result['manifest_sha256'])
    before=p.payload_identity(files)
    files['deployment/install-plan.json']=b'changed'
    assert p.payload_identity(files)==before
    files['engineering/tools/rras_history/production_entry.py']+=b'\n'
    assert p.payload_identity(files)!=before


@pytest.mark.parametrize('name', ['/etc/shadow','../outside','vendor/../outside','vendor//x','vendor/evil.pth',
                                  'vendor/__pycache__/x','engineering/tools/rras_history/host_acceptance.py'])
def test_package_path_allowlist(name):
    with pytest.raises(ValueError):p.safe_name(name)


@pytest.mark.parametrize('change',['unit','policy','plan','wrapper','payload','authorization'])
def test_rehashed_mutations_cannot_override_blueprint(package,change):
    destination,result=package;path=destination/'runtime-manifest.json';manifest=json.loads(path.read_bytes());common=p.common()
    if change=='authorization':manifest['activation_authorized']=True
    else:
        name={'unit':'deployment/rras-engineering-history.service','policy':'deployment/access-policy.json',
              'plan':'deployment/install-plan.json','wrapper':'deployment/rras-history-client',
              'payload':'engineering/tools/rras_history/production_entry.py'}[change]
        raw=(destination/name).read_bytes()+b'\nchanged\n';(destination/name).write_bytes(raw)
        manifest['files'][name]=hashlib.sha256(raw).hexdigest()
    raw=common.encoded(manifest);path.write_bytes(raw)
    with pytest.raises(ValueError):p.verify(destination,hashlib.sha256(raw).hexdigest())


def test_package_never_overwrites_existing_destination(package):
    destination,_=package
    with pytest.raises(FileExistsError):p.build(SOURCE,destination/'vendor',destination,'a'*40)


@pytest.mark.parametrize('ids', [[0],[996],[997],[True],['1000'],[2**32-1]])
def test_acl_identities_cannot_admit_root_workers_or_non_uid(ids):
    with pytest.raises(ValueError):entry.acl_spec(ids,directory=False)


def test_exact_acls_replace_old_named_and_default_entries_before_listen(env):
    root,store,_=env;runtime=root/'runtime';runtime.mkdir(mode=0o700)
    subprocess.run(['/usr/bin/setfacl','--set','u::rwx,g::---,o::---,u:2222:--x,m::--x',str(runtime)],check=True)
    subprocess.run(['/usr/bin/setfacl','-m','d:u::rwx,d:g::---,d:o::---,d:u:2222:rwx,d:m::rwx',str(runtime)],check=True)
    grants={os.getuid():{'private_read':['example'],'write':['example']},61082:{'private_read':['example'],'write':[]}}
    policy=dict(contract='engineering-history-access.v1',principals=[dict(uid=uid,**grant) for uid,grant in grants.items()])
    observed=[]
    def before_listen(path):
        entry.prepare_endpoint(path,grants)
        observed.append((acl(runtime),acl(path)))
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
            with pytest.raises(ConnectionRefusedError):client.connect(str(path))
    with u.Server(runtime/'service.sock',store,policy,on_bound=before_listen) as server:
        assert server.listener is not None
        assert 'user:61082:--x' in observed[0][0] and 'user:61082:rw-' in observed[0][1]
        assert '2222' not in observed[0][0] and '2222' not in observed[0][1]
        assert 'default:' not in observed[0][0]
        assert 'group::---' in observed[0][1] and 'other::---' in observed[0][1]
        assert server.path.stat().st_mode&0o777==0o660
    assert not (runtime/'service.sock').exists()


def test_failed_acl_setup_refuses_start_and_removes_only_new_socket(env):
    root,store,_=env
    def refused(path):raise subprocess.CalledProcessError(1,['/usr/bin/setfacl'])
    policy=dict(contract='engineering-history-access.v1',principals=[])
    with pytest.raises(subprocess.CalledProcessError):
        with u.Server(root/'service.sock',store,policy,on_bound=refused):pass
    assert not (root/'service.sock').exists() and store.history()['records']==[]


def test_acl_target_kind_and_symlink_checks(env):
    root,_,_=env;path=root/'regular';path.write_text('preserve')
    with pytest.raises(ValueError):entry.set_acl(path,[os.getuid()],directory=False)
    link=root/'link';link.symlink_to(root)
    with pytest.raises(ValueError):entry.set_acl(link,[os.getuid()],directory=True)


def test_entry_requires_expected_dedicated_account():
    class Account:pw_uid=os.getuid()+100
    with patch.object(entry.pwd,'getpwnam',return_value=Account()):
        with pytest.raises(ValueError):entry.require_account('rras-history')


def test_unit_keeps_service_passive_and_root_workflow_inaccessible():
    raw=p.service_unit('/opt/rras-engineering/releases/history-'+'a'*12).decode()
    for directive in ('User=rras-history','Group=rras-history','NoNewPrivileges=yes','PrivateNetwork=yes',
                      'RestrictAddressFamilies=AF_UNIX','ProtectSystem=strict','ProtectHome=yes',
                      'CapabilityBoundingSet=\n','Restart=no','RuntimeDirectoryPreserve=yes','KillMode=control-group'):
        assert directive in raw
    assert '/var/lib/rras-workflow' in raw and '/etc/rras-engineering/credentials' in raw
    assert 'SupplementaryGroups=' not in raw and 'LoadCredential=' not in raw
    assert 'initialize-empty' not in raw and 'ExecStartPre=' not in raw



def test_daemon_environment_is_an_allowlist_even_with_manager_credentials():
    with patch.dict(entry.os.environ,{'UNEXPECTED_CREDENTIAL':'synthetic','OPENAI_API_KEY':'synthetic'},clear=True):
        entry.service_environment()
        assert dict(entry.os.environ)=={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','LANG':'C.UTF-8'}


@pytest.mark.parametrize('uid',[0,996,997,1000])
def test_service_cannot_adopt_root_worker_or_interactive_identity(uid):
    with pytest.raises(ValueError):entry.require_account(str(uid))
