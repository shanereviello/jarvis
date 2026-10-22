"""Unprivileged manifest/custody/launch checks, not cross-UID host acceptance."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest
from test_engineering_history_local import module

p=module('history_acceptance_package');h=module('host_acceptance')
SOURCE=Path(__file__).resolve().parents[2]


@pytest.fixture
def payload(tmp_path):
    vendor=tmp_path/'vendor';vendor.mkdir();(vendor/'fixture.py').write_text('SYNTHETIC=True\n')
    candidate=tmp_path/'candidate'
    result=p.build(SOURCE,vendor,candidate,'a'*40)
    return candidate,result


def test_build_verify_exact_deterministic_manifest(payload,tmp_path):
    candidate,result=payload
    manifest,files=p.verify(candidate,result['manifest_sha256'])
    assert manifest['source_commit']=='a'*40 and set(p.SOURCE_FILES)<=set(files)
    assert result['root_mutations'] is False
    assert len(files)==len(p.SOURCE_FILES)+1
    for name,content in files.items():assert content==(candidate/name).read_bytes()
    vendor=tmp_path/'vendor';second=tmp_path/'second'
    assert p.build(SOURCE,vendor,second,'a'*40)==result


def test_changed_payload_refuses_before_staging(payload):
    candidate,result=payload
    (candidate/p.SOURCE_FILES[0]).write_text('changed\n')
    with pytest.raises(ValueError,match='digest'):p.verify(candidate,result['manifest_sha256'])


@pytest.mark.parametrize('name',['/etc/x','../x','vendor/../x','vendor//x','vendor/.git/config',
                                'vendor/__pycache__/x','vendor/evil.pth','vendor/x.pyc','engineering/not-allowed.py'])
def test_manifest_path_allowlist(name):
    with pytest.raises(ValueError):p.safe_name(name)


@pytest.mark.parametrize('change',['scope','missing','symlink','hardlink','traversal','oversize','duplicate'])
def test_invalid_manifest_payload_refused(payload,change):
    candidate,result=payload;path=candidate/'acceptance-manifest.json';manifest=json.loads(path.read_bytes())
    if change=='scope':manifest['scope']='production-install'
    if change=='missing':manifest['files'].pop(p.SOURCE_FILES[0])
    if change=='traversal':manifest['files']['../outside']='a'*64
    if change in ('symlink','hardlink','oversize'):
        target=candidate/'vendor/fixture.py'
        if change=='symlink':target.unlink();target.symlink_to(candidate/p.SOURCE_FILES[0])
        if change=='hardlink':os.link(target,candidate/'second-link')
        if change=='oversize':target.write_bytes(b'x'*(4*1024*1024+1))
    raw=p.encoded(manifest)
    if change=='duplicate':raw=b'{"contract":"x","contract":"x"}'
    path.write_bytes(raw)
    with pytest.raises(ValueError):p.verify(candidate,hashlib.sha256(raw).hexdigest())


def test_operator_helper_is_self_contained_stdlib_and_checks_sudo(tmp_path):
    helper=tmp_path/'helper.py';sha=p.emit_helper(helper)
    assert hashlib.sha256(helper.read_bytes()).hexdigest()==sha
    result=subprocess.run([sys.executable,'-I','-B',str(helper),'--candidate',str(tmp_path),
                           '--manifest-sha256','a'*64,'--state','/var/lib/rras-history-acceptance-20261022'],capture_output=True)
    assert result.returncode==1 and b'preserve protected' in result.stderr and not result.stdout
    assert 'from jsonschema' not in helper.read_text()


def test_rebuild_never_overwrites_existing_candidate(payload):
    candidate,_=payload
    with pytest.raises(FileExistsError):p.build(SOURCE,candidate/'vendor',candidate,'a'*40)


@pytest.mark.parametrize('name',['/var/lib/rras-workflow','/tmp/rras-history-acceptance-one',
                                '/var/lib/rras-history-acceptance-../x','/var/lib/rras-history-acceptance-'])
def test_fixture_path_refuses_unrelated_state(name):
    with pytest.raises(ValueError):h.fixture_path(name)


def test_launch_drops_uid_groups_caps_and_network_without_production_unit():
    state=h.fixture_path('/var/lib/rras-history-acceptance-test')
    command=h.command('rpc',state,h.CLIENT_A)
    assert command[:3]==['/usr/bin/unshare','--net','--']
    for flag in ('--no-new-privs','--bounding-set=-all','--inh-caps=-all','--ambient-caps=-all','--pdeathsig=TERM'):
        assert flag in command
    assert command[command.index('--reuid')+1]==str(h.CLIENT_A)
    assert command[command.index('--groups')+1]==str(h.SHARED)
    assert command[command.index('--regid')+1]==str(h.SHARED)
    assert 'systemctl' not in ' '.join(command) and 'docker' not in ' '.join(command)
    assert not any(key.startswith(('OPENAI_','CODEX_','GH_')) for key in h.ENV)
