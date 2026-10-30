"""Production entry policy boundary and hardened blueprint; no host activation."""
from types import SimpleNamespace
import pytest
from test_engineering_history_local import module
from test_history_curated_publication import catalog
from test_history_curated_preview import preview_inputs
from test_history_managed_link import setup,exporter,j,fixtures

entry=module('curated_service_entry');plan=module('curated_service_plan')


def test_empty_catalog_is_visible_without_publication(catalog):
    root,_,repo=catalog;answer=module('curated_publication').search(root,repo,'')
    assert answer['entries']==[] and answer['catalog_state']=='empty' and answer['generation_sha256'] is None
    assert answer['publication_recorded'] is False and answer['authority_granted'] is False
    with pytest.raises(ValueError):module('curated_publication').search(root,repo,'',generation_sha256='a'*64)
    with pytest.raises(ValueError):module('curated_publication').search(root,repo,'x'*257)


@pytest.mark.parametrize('uid',[1000,995])
def test_broader_principal_refused_before_socket_or_acl(uid,monkeypatch):
    real=entry.local;calls=[]
    transport=SimpleNamespace(load_policy=lambda _: {'policy':'fixture'})
    access=SimpleNamespace(Access=lambda *_:SimpleNamespace(grants={uid:['jarvis']}))
    monkeypatch.setattr(entry.os,'getuid',lambda:995)
    def local(name):
        if name=='unix':return transport
        if name=='curated_read_access':return access
        calls.append(name);return real(name)
    monkeypatch.setattr(entry,'local',local)
    with pytest.raises(ValueError,match='dedicated'):entry.serve('/catalog','/socket','/policy',lambda:True)
    assert 'curated_read_unix' not in calls and 'production_entry' not in calls


def test_exact_acl_readers_only_and_no_store_writer(monkeypatch,tmp_path):
    observed=[];policy={'contract':'fixture'};socket=tmp_path/'read.sock'
    class Server:
        def __init__(self,path,root,grants,on_bound):assert grants==policy;self.on_bound=on_bound
        def __enter__(self):self.on_bound(socket);return self
        def __exit__(self,*_):pass
    modules={'unix':SimpleNamespace(load_policy=lambda _:policy),
        'curated_read_access':SimpleNamespace(Access=lambda *_:SimpleNamespace(grants={61122:['jarvis'],61123:[]})),
        'production_entry':SimpleNamespace(set_acl=lambda path,ids,**kw:observed.append((path,ids,kw))),
        'curated_read_unix':SimpleNamespace(Server=Server)}
    monkeypatch.setattr(entry,'local',lambda name:modules[name])
    entry.serve('/catalog',socket,'/policy',lambda:True)
    assert observed==[(socket.parent,[61122],{'directory':True}),(socket,[61122],{'directory':False})]


def test_unit_readonly_catalog_runtime_only_and_private_paths_hidden():
    raw=plan.service_unit('/opt/rras-engineering/releases/curated-history-'+'a'*12).decode()
    assert 'User=rras-history' in raw and '--account 995' in raw
    assert 'ReadWritePaths=/run/rras-curated-history\n' in raw
    assert 'ReadOnlyPaths=/var/lib/rras-curated-history/catalog' in raw
    for name in ('/var/lib/rras-engineering-history','/run/rras-engineering-history','/var/lib/rras-workflow','/etc/rras-engineering/credentials','/run/docker.sock'):assert name in raw.split('InaccessiblePaths=',1)[1].split('\n',1)[0]
    for value in ('ProtectHome=yes','PrivateNetwork=yes','RestrictAddressFamilies=AF_UNIX','NoNewPrivileges=yes','CapabilityBoundingSet=\n','Restart=no'):assert value in raw
    with pytest.raises(ValueError):plan.service_unit('/tmp/untrusted\nExecStart=/bin/sh')


def test_unit_systemd_syntax(tmp_path):
    import shutil,subprocess
    if shutil.which('systemd-analyze') is None:pytest.skip('systemd-analyze unavailable')
    path=tmp_path/'rras-curated-history-read.service'
    path.write_bytes(plan.service_unit('/opt/rras-engineering/releases/curated-history-'+'a'*12))
    result=subprocess.run(['/usr/bin/systemd-analyze','verify',str(path)],capture_output=True,timeout=15)
    assert result.returncode==0,result.stderr.decode()
