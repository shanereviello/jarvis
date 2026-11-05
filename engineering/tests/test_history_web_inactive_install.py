"""Inactive installer contract/preflight emission tests. No privileged actions."""
from pathlib import Path
import hashlib
import json
import subprocess
import pytest
from test_history_web import web,TOOLS


def installer():
    prefix=(TOOLS/'production_package.py').read_text().split('\ndef build(',1)[0]
    suffix=(TOOLS/'inactive_install.py').read_text();namespace={'__name__':'fixture_installer'}
    exec(compile(prefix+'\n'+suffix,'fixture_installer','exec'),namespace)
    return namespace


def config():return dict(contract='engineering-history-web.v1',uid=993,gid=993,history_uid=995,
    history_socket='/run/rras-engineering-history/service.sock',repositories=['jarvis'],issuer='https://fixture.cloudflareaccess.com',
    audience='fixture-audience',email='owner@example.test',origin='https://history.example.test',bind='172.19.0.1',port=18764)


def test_root_guard_precedes_reads_and_installation():
    module=installer()
    with pytest.raises(ValueError,match='administrator'):module['install']('/not-read','0'*64,'/not-read','0'*64)


def test_exact_config_digest_and_scope():
    module=installer();raw=module['encoded'](config());sha=hashlib.sha256(raw).hexdigest()
    assert module['configuration'](raw,sha)==config()
    with pytest.raises(ValueError,match='digest'):module['configuration'](raw,'0'*64)


@pytest.mark.parametrize('field,value',[('uid',1000),('uid',True),('gid',995),('history_uid',993),('repositories',['other']),('bind','0.0.0.0'),('port',443),('history_socket','/tmp/socket')])
def test_reviewed_identity_repository_and_bind_changes_refused(field,value):
    module=installer();value_config=config();value_config[field]=value;raw=module['encoded'](value_config)
    with pytest.raises(ValueError):module['configuration'](raw,hashlib.sha256(raw).hexdigest())


def test_preflight_operation_returns_without_mutation(monkeypatch):
    module=installer();monkeypatch.setitem(module,'preflight',lambda *args:({'release':'/opt/example'},{},b'',Path('/not-created'),'1','a'*64))
    def mutation(*args,**kwargs):raise AssertionError('preflight attempted mutation')
    monkeypatch.setattr(module['os'],'umask',mutation)
    result=module['install']('/candidate','a'*64,'/config','b'*64,check_only=True)
    assert result['mutations'] is False and result['installation_authorized'] is False and result['activation_authorized'] is False


def test_new_identity_is_locked_no_home_no_login():
    argv=installer()['user_command']()
    assert argv[0]=='/usr/sbin/useradd' and argv[argv.index('--uid')+1]=='993'
    assert argv[argv.index('--password')+1]=='!' and argv[argv.index('--shell')+1]=='/usr/sbin/nologin'
    assert '--no-create-home' in argv and '--no-user-group' in argv and '--no-log-init' in argv


def test_emitted_helper_uses_committed_installer(tmp_path):
    source=tmp_path/'repo';folder=source/'engineering/tools/rras_history_web';folder.mkdir(parents=True)
    for name in ('production_package.py','inactive_install.py'):(folder/name).write_bytes((TOOLS/name).read_bytes())
    env={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','LANG':'C.UTF-8','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null'}
    def git(*args):return subprocess.check_output(['/usr/bin/git','-C',str(source),*args],env=env,stderr=subprocess.PIPE).decode().strip()
    git('init');git('add','.');git('-c','user.name=Fixture','-c','user.email=fixture@example.test','commit','-m','Fixture')
    original=(folder/'inactive_install.py').read_bytes();(folder/'inactive_install.py').write_bytes(b'raise RuntimeError("uncommitted")')
    path=tmp_path/'helper.py';result=web('install_package').emit(source,git('rev-parse','HEAD'),path)
    assert original in path.read_bytes() and hashlib.sha256(path.read_bytes()).hexdigest()==result['helper_sha256']
    compile(path.read_bytes(),str(path),'exec')


def test_identity_refuses_other_account_with_same_primary_group(monkeypatch):
    import types
    module=installer();name=module['ACCOUNT'];uid=module['UID']
    user=types.SimpleNamespace(pw_uid=uid,pw_gid=uid,pw_name=name,pw_dir='/nonexistent',pw_shell='/usr/sbin/nologin')
    other=types.SimpleNamespace(pw_uid=1001,pw_gid=uid,pw_name='other')
    monkeypatch.setattr(module['pwd'],'getpwnam',lambda value:user)
    monkeypatch.setattr(module['grp'],'getgrnam',lambda value:types.SimpleNamespace(gr_gid=uid,gr_mem=[]))
    monkeypatch.setattr(module['pwd'],'getpwall',lambda:[user,other])
    with pytest.raises(ValueError,match='primary group'):module['verify_identity']()
