"""Writer boundary plan and durable one-attempt launch behavior; no systemd start."""
import subprocess
from types import SimpleNamespace
import pytest
from test_engineering_history_local import module

m=module('curated_publication_launch')
RELEASE='/opt/rras-engineering/releases/curated-history-'+'a'*12
SHA='b'*64


def test_fixed_catalog_only_write_and_provider_free_command():
    argv=m.command(RELEASE,SHA)
    props=[argv[i+1] for i,value in enumerate(argv) if value=='--property']
    assert [p for p in props if p.startswith('ReadWritePaths=')]==['ReadWritePaths='+m.CATALOG]
    for value in ('User=rras-history','ProtectSystem=strict','ProtectHome=yes','PrivateNetwork=yes',
                  'NoNewPrivileges=yes','CapabilityBoundingSet=','AmbientCapabilities=',
                  'RuntimeMaxSec=60s','KillMode=control-group','Restart=no'):assert value in props
    hidden=next(p for p in props if p.startswith('InaccessiblePaths='))
    for value in ('/var/lib/rras-engineering-history','/run/rras-engineering-history','/run/docker.sock','/var/lib/rras-curated-publications'):assert value in hidden
    assert argv[argv.index('--')+1:][:2]==['/usr/bin/env','-i']
    assert '--unit=rras-curated-publication.service' in argv
    assert argv[-2:]==['--reviewed-request-sha256',SHA]


@pytest.mark.parametrize('release,sha',[('/tmp/code',SHA),(RELEASE+'\nExecStart=/bin/sh',SHA),(RELEASE,'x'),(RELEASE,'b'*65)])
def test_invalid_selection_before_any_execution(release,sha):
    with pytest.raises(ValueError):m.command(release,sha)


def test_operator_preflight_refuses_before_payload_read():
    with pytest.raises(ValueError,match='administrator'):m.preflight(RELEASE,SHA)


def fixture(monkeypatch,tmp_path):
    attempts=tmp_path/'attempts';attempts.mkdir(mode=0o700)
    monkeypatch.setattr(m,'ATTEMPTS',attempts)
    monkeypatch.setattr(m,'preflight',lambda *_:(['fixture-only'],b'{}'))
    return attempts


def test_fence_output_and_replay_refusal(monkeypatch,tmp_path):
    attempts=fixture(monkeypatch,tmp_path);calls=[]
    def run(argv,**kw):
        calls.append((argv,kw));return SimpleNamespace(returncode=0,stdout=b'private receipt',stderr=b'')
    monkeypatch.setattr(m.subprocess,'run',run)
    answer=m.launch(RELEASE,SHA)
    assert answer=={'writer_returned':True,'publication_verified':False,'automatic_retry':False}
    assert (attempts/SHA/'stdout').read_bytes()==b'private receipt'
    assert calls[0][1]['env']==m.ENV and calls[0][1]['input']==b'{}'
    with pytest.raises(FileExistsError):m.launch(RELEASE,SHA)
    assert len(calls)==1


def test_timeout_keeps_attempt_and_does_not_stop_or_retry(monkeypatch,tmp_path):
    attempts=fixture(monkeypatch,tmp_path);calls=[]
    def run(*args,**kw):
        calls.append(args);raise subprocess.TimeoutExpired('fixture',75)
    monkeypatch.setattr(m.subprocess,'run',run)
    with pytest.raises(subprocess.TimeoutExpired):m.launch(RELEASE,SHA)
    assert (attempts/SHA/'started').exists()
    with pytest.raises(FileExistsError):m.launch(RELEASE,SHA)
    assert len(calls)==1


def test_plan_systemd_syntax(tmp_path):
    argv=m.command(RELEASE,SHA)
    props=[argv[i+1] for i,value in enumerate(argv) if value=='--property']
    # Verify syntax without running the root launcher or starting a service.
    unit=tmp_path/'rras-curated-publication.service'
    unit.write_text('[Service]\nType=exec\n'+'\n'.join(props)+'\nExecStart=/usr/bin/true\n')
    result=subprocess.run(['/usr/bin/systemd-analyze','verify',str(unit)],capture_output=True,timeout=15)
    assert result.returncode==0,result.stderr.decode()
