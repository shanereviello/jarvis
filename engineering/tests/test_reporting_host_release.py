import importlib.util
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).parents[1]
MODULE=ROOT/'tools/rras_reporting/host_release.py'
spec=importlib.util.spec_from_file_location('reporting_host_release',MODULE)
release=importlib.util.module_from_spec(spec);spec.loader.exec_module(release)
SITE=Path('/home/shanereviello/Documents/Codex/2026-11-04/files-mentioned-by-the-user-engineering/work/project-test-venv/lib/python3.13/site-packages')
BINARY=Path('/home/shanereviello/.codex/packages/standalone/releases/0.159.0-x86_64-unknown-linux-musl/bin/codex')


def test_release_vendor_is_exact_and_imports_without_global_site_packages(tmp_path):
    files=release.site_packages(SITE)
    assert all(name.startswith('vendor/site-packages/') for name in files)
    assert not any('/pytest/' in name or '/playwright/' in name or name.endswith('direct_url.json') for name in files)
    vendor=tmp_path/'vendor/site-packages'
    for name,raw in files.items():
        path=tmp_path/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    program="import sys;sys.path.insert(0,sys.argv[1]);import mcp.server.fastmcp,jsonschema;print(mcp.__version__ if hasattr(mcp,'__version__') else 'mcp-ok',jsonschema.__version__)"
    result=subprocess.run([sys.executable,'-I','-c',program,str(vendor)],capture_output=True,text=True,check=True,timeout=30)
    assert 'mcp-ok' in result.stdout and '4.26.0' in result.stdout


def test_isolated_venv_reads_only_the_release_vendor_path(tmp_path):
    files=release.site_packages(SITE)
    vendor=tmp_path/'vendor/site-packages'
    for name,raw in files.items():
        path=tmp_path/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    venv=tmp_path/'venv'
    subprocess.run([sys.executable,'-m','venv','--without-pip',str(venv)],check=True,timeout=30)
    site=venv/'lib/python3.13/site-packages';site.mkdir(parents=True,exist_ok=True)
    (site/'rras-vendor.pth').write_text(str(vendor)+'\n')
    result=subprocess.run([str(venv/'bin/python'),'-I','-c',
        'import mcp.server.fastmcp,jsonschema;print(jsonschema.__version__)'],
        capture_output=True,text=True,check=True,timeout=30)
    assert result.stdout.strip()=='4.26.0'


def test_release_inputs_and_digest_are_canonical():
    assert release.safe_relative('engineering/tools/rras_reporting/host_release.py')
    for bad in ('/etc/passwd','../outside','engineering/../outside',''):
        try:release.safe_relative(bad)
        except ValueError:pass
        else:raise AssertionError('unsafe package path accepted')
    binary=release.binaries(BINARY)
    assert release.digest(binary['runtime/bin/codex'])==release.CODEX_SHA256
    first=release.release_digest({'a':b'one','b':b'two'})
    assert first==release.release_digest({'b':b'two','a':b'one'})


def test_release_renders_every_systemd_path_and_python_vendor_binding():
    files=release.source_files(ROOT.parent)
    target='/opt/rras-engineering/releases/standardized-history-a1b2c3d4e5f6'
    rendered=release.render_release(files,target)
    assert rendered['runtime/rras-vendor-site-packages.pth']==(target+'/vendor/site-packages\n').encode()
    for name,raw in rendered.items():
        if name.startswith('engineering/systemd/'):
            assert b'standardized-history-runtime' not in raw
            if b'/opt/rras-engineering/releases/standardized-history-' in files[name]:
                assert target.encode() in raw
