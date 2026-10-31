"""Offline container/reader fixture plans; actual systemd and Docker checks need sudo."""
import hashlib
import importlib.util
from pathlib import Path
import pytest
from test_engineering_history_local import module
p=module('curated_container_package');d=module('curated_container_driver')


def test_reader_blueprint_has_only_fixture_reader_and_paths():
    argv=d.reader_command();props=[argv[i+1] for i,v in enumerate(argv) if v=='--property']
    assert '--unit='+d.UNIT in argv and 'rras-curated-history-read.service' not in argv
    for value in ('User='+d.ACCOUNT,'ProtectSystem=strict','PrivateNetwork=yes','NoNewPrivileges=yes','CapabilityBoundingSet=',
                  'ReadOnlyPaths='+str(d.STATE/'private/catalog'),'ReadWritePaths='+str(d.RUNTIME)):assert value in props
    assert d.policy()['principals']==[{'uid':61158,'repositories':['example_library']}]
    assert d.policy(False)['principals']==[]
    assert all(item['uid'] not in (0,1000,61157) for item in d.policy()['principals'])


def test_pinned_container_mounts_only_code_and_socket_with_root_drop():
    argv=d.container_command('read');mounts=[argv[i+1] for i,value in enumerate(argv) if value=='--mount']
    assert len(mounts)==2 and all(item.endswith(',readonly') for item in mounts)
    assert all('/private' not in item and '/srv/' not in item for item in mounts)
    assert d.IMAGE in argv and '--pull=never' in argv
    assert argv[argv.index('--network')+1]=='none'
    for flag in ('--read-only','--clear-groups','--bounding-set=-all','--inh-caps=-all','--ambient-caps=-all','--no-new-privs'):assert flag in argv
    assert argv[argv.index('--reuid')+1]=='61158'
    with pytest.raises(ValueError):d.container_command('read',0)
    with pytest.raises(ValueError):d.container_command('denied',42)


def test_operator_root_controller_denied_before_any_action():
    with pytest.raises(ValueError,match='sudo'):d.run()


def test_pinned_package_and_stdlib_bootstrap(tmp_path):
    root=tmp_path/'candidate';root.mkdir()
    files={name:b'fixture\n' for name in p.SOURCE_FILES};files['vendor/dependency.py']=b'pass\n'
    for name,raw in files.items():
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    manifest={'contract':'engineering-curated-container-host.v1','scope':'isolated-synthetic-only','source_commit':'a'*40,
              'files':{name:hashlib.sha256(raw).hexdigest() for name,raw in files.items()}}
    raw=p.encoded(manifest);(root/p.MANIFEST).write_bytes(raw);sha=hashlib.sha256(raw).hexdigest()
    assert p.verify(root,sha)[0]==manifest and p.STATE==d.STATE
    helper=tmp_path/'helper.py';p.emit_helper(helper)
    spec=importlib.util.spec_from_file_location('container_bootstrap',helper);boot=importlib.util.module_from_spec(spec);spec.loader.exec_module(boot)
    assert boot.verify(root,sha)[0]==manifest
    assert 'curated_container_driver.py' in helper.read_text()
    (root/'vendor/dependency.py').write_text('changed')
    with pytest.raises(ValueError):p.verify(root,sha)


def test_mcp_client_error_flag_across_sdk_models():
    from types import SimpleNamespace
    probe=module('curated_container_probe')
    assert probe.is_error(SimpleNamespace(is_error=True))
    assert probe.is_error(SimpleNamespace(isError=True))
    assert not probe.is_error(SimpleNamespace(is_error=False))
    with pytest.raises(AttributeError):probe.is_error(SimpleNamespace())


@pytest.mark.parametrize('message',[b'Error: No such object: fixture',b'error: no such object: fixture',b'Error: No such container: fixture'])
def test_docker_missing_case_variants(message):
    from types import SimpleNamespace
    assert d.container_absent(SimpleNamespace(returncode=1,stderr=message))


@pytest.mark.parametrize('code,message',[(0,b''),(1,b'permission denied'),(1,b'Cannot connect to Docker daemon'),(1,b'no such file or directory')])
def test_docker_other_errors_do_not_count_as_absent(code,message):
    from types import SimpleNamespace
    assert not d.container_absent(SimpleNamespace(returncode=code,stderr=message))


def test_effective_catalog_read_only_even_without_exact_mount_entry(monkeypatch):
    from types import SimpleNamespace
    import os
    seen=[]
    def readonly(path):seen.append(path);return SimpleNamespace(f_flag=os.ST_RDONLY)
    monkeypatch.setattr(d.os,'statvfs',readonly)
    d.verify_catalog_read_only(Path('/proc/123'),Path('/var/lib/synthetic/catalog'))
    assert seen==[Path('/proc/123/root/var/lib/synthetic/catalog')]
    monkeypatch.setattr(d.os,'statvfs',lambda _:SimpleNamespace(f_flag=0))
    with pytest.raises(ValueError,match='not read-only'):d.verify_catalog_read_only(Path('/proc/123'),Path('/var/lib/synthetic/catalog'))


@pytest.mark.parametrize('pid',[0,123])
def test_curated_client_authenticates_exact_uid_across_pid_namespaces(pid):
    import struct
    from types import SimpleNamespace
    wire=module('curated_read_unix')
    connection=SimpleNamespace(getsockopt=lambda *_:struct.pack('iII',pid,61157,61157))
    assert wire.server_peer(connection,61157)==61157


@pytest.mark.parametrize('pid,uid',[(-1,61157),(0,0),(0,61158),(123,61158)])
def test_curated_client_refuses_invalid_pid_or_wrong_kernel_uid(pid,uid):
    import struct
    from types import SimpleNamespace
    wire=module('curated_read_unix')
    connection=SimpleNamespace(getsockopt=lambda *_:struct.pack('iII',pid,uid,uid))
    with pytest.raises(ValueError):wire.server_peer(connection,61157)


def test_private_transport_keeps_positive_pid_requirement():
    import struct
    from types import SimpleNamespace
    wire=module('unix')
    connection=SimpleNamespace(getsockopt=lambda *_:struct.pack('iII',0,61157,61157))
    with pytest.raises(ValueError,match='live peer'):wire.peer(connection)
