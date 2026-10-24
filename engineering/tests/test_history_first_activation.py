"""First-activation boundaries and generated-tool checks; no live unit mutation."""
import ast
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from test_engineering_history_local import module

builder=module('activation_package');runtime=module('production_package')
SOURCE=Path(__file__).resolve().parents[2]


@pytest.fixture
def tool(tmp_path):
    helper=tmp_path/'activate.py';builder.emit_helper(helper)
    spec=importlib.util.spec_from_file_location('generated_activation',helper)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result)
    return result


def test_generated_tool_verifies_exact_existing_runtime(tool,tmp_path):
    vendor=tmp_path/'vendor';vendor.mkdir();(vendor/'fixture.py').write_text('SYNTHETIC=True\n')
    candidate=tmp_path/'candidate';result=runtime.build(SOURCE,vendor,candidate,'a'*40)
    manifest,files=tool.verify(candidate,result['manifest_sha256'])
    assert manifest['activation_authorized'] is False
    assert files['deployment/rras-engineering-history.service']==runtime.service_unit(manifest['release'])
    assert 'activation_probe.py' not in ' '.join(files)


def test_unprivileged_activation_refused_before_reads(tool,monkeypatch,tmp_path):
    monkeypatch.setattr(tool.os,'getuid',lambda:1000)
    with pytest.raises(ValueError,match='administrator'):tool.activate(tmp_path,'a'*64)


def test_preflight_only_cannot_create_activation_journal(tool,monkeypatch,tmp_path):
    path=tmp_path/'journal'
    monkeypatch.setattr(tool,'activation_preflight',lambda *_:(995,995,path))
    value=tool.activate(tmp_path,'a'*64,check_only=True)
    assert value['mutations'] is False and value['activation_authorized'] is False
    assert not path.exists()


@pytest.mark.parametrize('uid,role',[(0,'reader'),(995,'reader'),(1000,'worker-denial'),(996,'reader'),(1000,'execute')])
def test_unknown_probe_identity_or_role_refused(tool,uid,role,tmp_path):
    with pytest.raises(ValueError):tool.probe_command(tmp_path,uid,995,role)


@pytest.mark.parametrize('uid,role',[(1000,'reader'),(996,'worker-denial'),(997,'worker-denial')])
def test_probes_have_no_groups_caps_network_or_root(tool,uid,role,tmp_path):
    command=tool.probe_command(tmp_path,uid,995,role)
    assert command[:3]==['/usr/bin/unshare','--net','--']
    assert command[command.index('--reuid')+1]==str(uid)
    assert command[command.index('--regid')+1]==str(uid)
    for flag in ('--clear-groups','--no-new-privs','--bounding-set=-all','--inh-caps=-all','--ambient-caps=-all'):
        assert flag in command


def test_probe_has_read_only_rpc_and_no_submission_route(tool):
    tree=ast.parse(tool.ACTIVATION_PROBE)
    methods=[]
    for node in ast.walk(tree):
        if isinstance(node,ast.Dict):
            for key,value in zip(node.keys,node.values):
                if isinstance(key,ast.Constant) and key.value=='method' and isinstance(value,ast.Constant):methods.append(value.value)
    assert set(methods)=={'history','execute'} # execute must be refused
    assert 'submit' not in methods


def test_activation_failure_preserves_journal_without_stop_or_enable(tool,tmp_path,monkeypatch):
    journal=tmp_path/'journal'
    monkeypatch.setattr(tool,'activation_preflight',lambda *_:(995,995,journal))
    monkeypatch.setattr(tool.os,'chown',lambda *_:None)
    monkeypatch.setattr(tool.os,'fchown',lambda *_:None)
    seen=[]
    def failed(command):
        seen.append(command)
        return SimpleNamespace(returncode=1,stdout=b'',stderr=b'synthetic start refusal')
    monkeypatch.setattr(tool,'command',failed)
    with pytest.raises(ValueError,match='preserve live state'):tool.activate(tmp_path,'a'*64)
    assert seen==[['/usr/bin/systemctl','start',tool.UNIT]]
    assert (journal/'failure-private.txt').exists()
    assert not (journal/'complete.json').exists()
    with pytest.raises(FileExistsError):tool.activate(tmp_path,'a'*64)


def test_live_identity_caps_and_namespace_are_checked(tool,monkeypatch):
    monkeypatch.setattr(tool,'status',lambda:{'ActiveState':'active','MainPID':'123'})
    fields='Uid:\t995\t995\t995\t995\nGid:\t995\t995\t995\t995\nGroups:\t995\nNoNewPrivs:\t1\n'+''.join(n+':\t0\n' for n in ('CapEff','CapPrm','CapInh','CapBnd','CapAmb'))
    monkeypatch.setattr(tool.Path,'read_text',lambda _:fields)
    monkeypatch.setattr(tool.os,'readlink',lambda p:'isolated' if '/123/' in p else 'host')
    assert tool.service_boundary(995,995)==123
    with pytest.raises(ValueError,match='identity'):tool.service_boundary(1000,995)
    monkeypatch.setattr(tool.os,'readlink',lambda _:'same')
    with pytest.raises(ValueError,match='network'):tool.service_boundary(995,995)


@pytest.mark.parametrize('fail_reader',[False,True])
def test_boot_enablement_occurs_only_after_all_read_only_checks(tool,tmp_path,monkeypatch,fail_reader):
    journal=tmp_path/'journal'
    monkeypatch.setattr(tool,'activation_preflight',lambda *_:(995,995,journal))
    monkeypatch.setattr(tool.os,'chown',lambda *_:None);monkeypatch.setattr(tool.os,'fchown',lambda *_:None)
    original_exists=tool.Path.exists
    monkeypatch.setattr(tool.Path,'exists',lambda p:True if str(p)==str(tool.RUNTIME/'service.sock') else original_exists(p))
    monkeypatch.setattr(tool,'service_boundary',lambda *_:123)
    checks=[]
    monkeypatch.setattr(tool,'empty_database',lambda *_:checks.append('database-checked'))
    monkeypatch.setattr(tool,'status',lambda:{'UnitFileState':'enabled'})
    def run(self,argv,tag):
        checks.append(tag)
        if tag.startswith('probe-'):
            uid=int(tag.removeprefix('probe-'))
            return SimpleNamespace(stdout=json.dumps({'uid':uid,'private_files_denied':not(fail_reader and uid==1000)}).encode())
        return SimpleNamespace(stdout=b'')
    monkeypatch.setattr(tool.Install,'run',run)
    if fail_reader:
        with pytest.raises(ValueError,match='preserve live state'):tool.activate(tmp_path,'a'*64)
        assert 'enable-history-at-boot' not in checks
    else:
        result=tool.activate(tmp_path,'a'*64)
        assert result['production_records_added']==0 and result['api_calls']==0
        assert checks==['start-history','probe-1000','probe-996','probe-997','database-checked','enable-history-at-boot']
