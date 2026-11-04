"""Startup contract tests; actual root ownership/UID/unit proof remains host work."""
from pathlib import Path
import pytest
from test_history_web import web,ISSUER,AUDIENCE,EMAIL,ORIGIN

entry=web('entry')

def config():
    return dict(contract='engineering-history-web.v1',uid=993,gid=993,history_uid=995,
        history_socket='/run/rras-engineering-history/service.sock',repositories=['jarvis'],
        issuer=ISSUER,audience=AUDIENCE,email=EMAIL,origin=ORIGIN,bind='127.0.0.1',port=18764)


def test_explicit_configuration_and_no_default_role():
    assert entry.configuration(config())==config()
    for field in config():
        value=config();value.pop(field)
        with pytest.raises((ValueError,TypeError)):entry.configuration(value)
    value=config();value['extra']='ignored'
    with pytest.raises(ValueError):entry.configuration(value)


@pytest.mark.parametrize('field,value',[
    ('uid',0),('uid',1000),('uid',995),('uid',996),('uid',True),('gid',994),('history_uid',993),
    ('history_socket','relative.sock'),('history_socket','/run/../tmp/test.sock'),
    ('repositories',[]),('repositories',['jarvis','jarvis']),('repositories',['../other']),
    ('issuer','https://other.example.test'),('origin','http://history.example.test'),
    ('bind','0.0.0.0'),('bind','::1'),('bind','example.test'),('bind','8.8.8.8'),('bind','169.254.1.2'),
    ('port',443),('port',True),('port',65536)])
def test_invalid_config_refused(field,value):
    changed=config();changed[field]=value
    with pytest.raises((ValueError,TypeError)):entry.configuration(changed)


@pytest.mark.parametrize('bind',['127.0.0.1','192.168.30.3','172.18.0.1','10.0.0.1'])
def test_explicit_private_bind_has_no_automatic_network_change(bind):
    value=config();value['bind']=bind;assert entry.configuration(value)['bind']==bind


def test_server_has_no_proxy_reload_websocket_or_request_log():
    options=entry.server_options(config())
    assert options['host']=='127.0.0.1' and options['port']==18764
    assert options['proxy_headers'] is False and options['forwarded_allow_ips']==[]
    assert options['access_log'] is False and options['log_config'] is None
    assert options['reload'] is False and options['workers']==1 and options['ws']=='none'
    assert options['limit_concurrency']==16 and options['timeout_graceful_shutdown']==10


def test_unprotected_configuration_refused(tmp_path):
    path=tmp_path/'config.json';path.write_text('{}');path.chmod(0o640)
    with pytest.raises(ValueError):entry.protected_configuration(path)
    link=tmp_path/'link';link.symlink_to(path)
    with pytest.raises(ValueError):entry.protected_configuration(link)


def test_identity_and_capability_guards(tmp_path,monkeypatch):
    value=config();status=tmp_path/'status'
    status.write_text('NoNewPrivs:\t1\n'+''.join(k+':\t0000000000000000\n' for k in ('CapInh','CapPrm','CapEff','CapBnd','CapAmb')))
    for name in ('getuid','geteuid','getgid','getegid'):monkeypatch.setattr(entry.os,name,lambda:993)
    monkeypatch.setattr(entry.os,'getgroups',lambda:[])
    entry.identity(value,status)
    monkeypatch.setattr(entry.os,'getgroups',lambda:[995])
    with pytest.raises(ValueError):entry.identity(value,status)
    monkeypatch.setattr(entry.os,'getgroups',lambda:[])
    status.write_text(status.read_text().replace('NoNewPrivs:\t1','NoNewPrivs:\t0'))
    with pytest.raises(ValueError):entry.identity(value,status)
    status.write_text('NoNewPrivs:\t1\nCapEff:\t1\n')
    with pytest.raises(ValueError):entry.identity(value,status)


def test_main_clears_provider_environment_and_passes_fixed_options(monkeypatch):
    import types,sys
    fake_environment={'OPENAI_API_KEY':'synthetic-secret','HTTPS_PROXY':'synthetic-proxy','PYTHONPATH':'untrusted'}
    monkeypatch.setattr(entry.os,'environ',fake_environment)
    monkeypatch.setattr(entry.os,'umask',lambda value:None)
    monkeypatch.setattr(entry.logging,'disable',lambda value:None)
    monkeypatch.setattr(entry,'protected_configuration',lambda path:config())
    monkeypatch.setattr(entry,'identity',lambda value:None)
    sentinel=object();monkeypatch.setattr(entry,'application',lambda value:sentinel)
    calls=[];monkeypatch.setitem(sys.modules,'uvicorn',types.SimpleNamespace(run=lambda app,**kw:calls.append((app,kw))))
    entry.main(['--config','/etc/synthetic.json'])
    assert fake_environment=={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','LANG':'C.UTF-8'}
    assert calls==[(sentinel,entry.server_options(config()))]


def test_main_refusal_does_not_emit_private_error(monkeypatch,capsys):
    monkeypatch.setattr(entry.os,'environ',{})
    monkeypatch.setattr(entry.os,'umask',lambda value:None)
    monkeypatch.setattr(entry.logging,'disable',lambda value:None)
    def refused(path):raise ValueError('PRIVATE_CONFIGURATION_CONTENT')
    monkeypatch.setattr(entry,'protected_configuration',refused)
    with pytest.raises(SystemExit) as error:entry.main(['--config','/etc/synthetic.json'])
    assert error.value.code==1
    assert 'PRIVATE_CONFIGURATION_CONTENT' not in capsys.readouterr().err
