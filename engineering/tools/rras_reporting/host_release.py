"""Prepare a hash-pinned, inactive Codex runtime release; never install it."""
import argparse
import hashlib
import importlib.metadata
import importlib.machinery
import json
import os
from pathlib import Path,PurePosixPath
import re
import shutil
import stat
import subprocess

CODEX_SHA256='d2752c52353401f7f6efbfcea68796f4f7a3d3e4769f5d1da53fa49d4856b72f'
SPECSTORY_SHA256='25b8a1b7c13b6cccd514845608785057b980ad3d55029d75527a0d9aaf0603c4'
DEPENDENCIES={
 'annotated-types':'0.8.0','anyio':'4.16.0','attrs':'26.1.0','certifi':'2026.10.23','cffi':'2.1.1','click':'8.5.1','cryptography':'50.0.2',
 'h11':'0.16.0','httpcore':'1.0.9','httpx':'0.28.1','httpx-sse':'0.4.3','idna':'3.20',
 'jsonschema':'4.26.0','jsonschema-specifications':'2025.9.1','mcp':'1.27.2','pydantic':'2.14.3',
 'pydantic-core':'2.50.4','pydantic-settings':'2.16.2','pyjwt':'2.15.1','python-multipart':'0.0.33',
 'python-dotenv':'1.2.4','pycparser':'3.12','referencing':'0.37.0','rpds-py':'2026.9.1','sse-starlette':'3.6.0',
 'starlette':'1.10.0','typing-extensions':'4.16.0','typing-inspection':'0.4.5','uvicorn':'0.54.0'
}
IMPORTS=('annotated_types','anyio','attr','attrs','certifi','click','h11','httpcore','httpx','httpx_sse','idna',
 'jsonschema','jsonschema_specifications','mcp','multipart','pydantic','pydantic_core','pydantic_settings',
 'referencing','rpds','sse_starlette','starlette','typing_extensions','typing_inspection','uvicorn','jwt','dotenv',
 'cryptography','cffi','pycparser','_cffi_backend')


def digest(raw):return hashlib.sha256(raw).hexdigest()


def safe_relative(name):
    if type(name) is not str:raise ValueError('relative package path required')
    path=PurePosixPath(name)
    if path.is_absolute() or str(path)!=name or any(part in ('','.','..') for part in path.parts):
        raise ValueError('safe relative package path required')
    return path


def regular(path):
    path=Path(path);info=path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:raise ValueError('regular single-link source required')
    raw=path.read_bytes()
    if len(raw)>512*1024*1024:raise ValueError('bounded package member required')
    return raw


def site_packages(files):
    """Copy only pinned runtime import roots and inert distribution metadata."""
    root=Path(files).resolve(strict=True);found={}
    distributions={d.metadata['Name'].lower().replace('_','-'):d for d in importlib.metadata.distributions(path=[str(root)])}
    if set(DEPENDENCIES)-set(distributions):raise ValueError('complete pinned runtime dependency set required')
    for name,version in DEPENDENCIES.items():
        distribution=distributions[name]
        if distribution.version!=version:raise ValueError('runtime dependency version differs: '+name)
        path=Path(distribution._path)
        for metadata in ('METADATA','WHEEL','entry_points.txt','top_level.txt'):
            member=path/metadata
            if member.is_file():found['vendor/site-packages/'+path.name+'/'+metadata]=regular(member)
    for name in IMPORTS:
        members=[root/name,root/(name+'.py')]+[root/(name+suffix) for suffix in importlib.machinery.EXTENSION_SUFFIXES]
        available=[member for member in members if member.exists()]
        if not available:raise ValueError('runtime import package unavailable: '+name)
        for source in available:
            entries=[source,*source.rglob('*')] if source.is_dir() else [source]
            for member in entries:
                if member.is_dir():continue
                relative=member.relative_to(root).as_posix()
                if '__pycache__' in member.parts or member.suffix=='.pyc':continue
                found['vendor/site-packages/'+relative]=regular(member)
    return found


def source_files(root):
    root=Path(root).resolve(strict=True);files={}
    for folder in ('engineering/tools/rras_reporting','engineering/tools/rras_history'):
        for path in sorted((root/folder).glob('*.py')):
            rel=path.relative_to(root).as_posix();files[rel]=regular(path)
    for path in sorted((root/'engineering/tools/rras_reporting').glob('*.js')):
        rel=path.relative_to(root).as_posix();files[rel]=regular(path)
    # The separate operator/browser entries reuse only the existing signed
    # Access verifier and hardened server options, not the dashboard itself.
    for name in ('access.py','entry.py'):
        path=root/'engineering/tools/rras_history_web'/name
        rel=path.relative_to(root).as_posix();files[rel]=regular(path)
    for name in ('__init__.py','plugin.yaml'):
        path=root/'engineering/hermes_plugins/engineering-reporting'/name
        rel=path.relative_to(root).as_posix();files[rel]=regular(path)
    for folder in ('engineering/contracts',):
        for path in sorted((root/folder).glob('*.json')):
            rel=path.relative_to(root).as_posix();files[rel]=regular(path)
    for path in sorted((root/'engineering/contracts').glob('linear-*.sql')):
        rel=path.relative_to(root).as_posix();files[rel]=regular(path)
    for path in sorted((root/'engineering/systemd').iterdir()):
        if path.is_file() and not path.is_symlink():
            rel=path.relative_to(root).as_posix();files[rel]=regular(path)
    return files


def binaries(binary,specstory=None):
    path=Path(binary).resolve(strict=True)
    if digest(regular(path))!=CODEX_SHA256:raise ValueError('reviewed Codex 0.159.0 executable required')
    base=path.parent;root=base.parent
    result={'runtime/bin/codex':regular(path)}
    required={
        'runtime/bin/codex-code-mode-host':base/'codex-code-mode-host',
        'runtime/codex-resources/bwrap':root/'codex-resources/bwrap',
        'runtime/codex-resources/zsh/bin/zsh':root/'codex-resources/zsh/bin/zsh',
        'runtime/codex-path/rg':root/'codex-path/rg'}
    for name,source in required.items():
        data=regular(source)
        if not os.access(source,os.X_OK):raise ValueError('reviewed executable resource required')
        result[name]=data
    if specstory is not None:
        source=Path(specstory).resolve(strict=True);data=regular(source)
        if digest(data)!=SPECSTORY_SHA256 or not os.access(source,os.X_OK):
            raise ValueError('reviewed SpecStory 2.17.0 executable required')
        result['runtime/bin/specstory']=data
    return result


def release_digest(files):
    inventory={name:digest(raw) for name,raw in sorted(files.items())}
    return digest(json.dumps(inventory,sort_keys=True,separators=(',',':')).encode()),inventory


def render_release(files,release):
    if not re.fullmatch('/opt/rras-engineering/releases/standardized-history-[0-9a-f]{12}',release):
        raise ValueError('canonical immutable release path required')
    rendered={}
    for name,raw in files.items():
        if name.startswith('engineering/systemd/'):
            rendered[name]=raw.replace(b'/opt/rras-engineering/releases/standardized-history-runtime',release.encode())
        else:
            rendered[name]=raw
    # Python -I still loads the isolated venv's site-packages. This inert path
    # file makes only this release's exact vendored libraries visible there.
    rendered['runtime/rras-vendor-site-packages.pth']=(release+'/vendor/site-packages\n').encode()
    return rendered


def verify(candidate,expected_manifest_sha256):
    candidate=Path(candidate)
    if (not candidate.is_absolute() or candidate.resolve(strict=True)!=candidate or
            type(expected_manifest_sha256) is not str or not re.fullmatch('[0-9a-f]{64}',expected_manifest_sha256)):
        raise ValueError('canonical candidate and manifest digest required')
    manifest_path=candidate/'manifest.json';manifest_raw=regular(manifest_path)
    if digest(manifest_raw)!=expected_manifest_sha256:raise ValueError('release manifest digest differs')
    manifest=json.loads(manifest_raw,object_pairs_hook=lambda pairs: _unique_object(pairs))
    if (type(manifest) is not dict or set(manifest)!={'contract','source_commit','release','payload_sha256',
            'codex_binary_sha256','dependencies','installed','activated','files'} or
            json.dumps(manifest,sort_keys=True,indent=2).encode()+b'\n'!=manifest_raw or
            manifest['contract']!='rras-codex-runtime-release.v1' or manifest['installed'] is not False or
            manifest['activated'] is not False or type(manifest['source_commit']) is not str or
            not re.fullmatch('[0-9a-f]{40}',manifest['source_commit']) or manifest['dependencies']!=DEPENDENCIES or
            type(manifest['files']) is not dict or not 1<=len(manifest['files'])<=2048):
        raise ValueError('valid inactive runtime release manifest required')
    release=manifest['release']
    if not re.fullmatch('/opt/rras-engineering/releases/standardized-history-[0-9a-f]{12}',release):
        raise ValueError('manifest release path differs')
    files={};total=0
    for name,expected in manifest['files'].items():
        safe_relative(name)
        if type(expected) is not str or not re.fullmatch('[0-9a-f]{64}',expected):raise ValueError('file digest required')
        raw=regular(candidate/name);total+=len(raw)
        if total>1024*1024*1024 or digest(raw)!=expected:raise ValueError('release member digest differs')
        files[name]=raw
    entries=list(candidate.rglob('*'))
    if any(path.is_symlink() for path in entries):raise ValueError('release tree cannot contain symlinks')
    observed={path.relative_to(candidate).as_posix() for path in entries if path.is_file()}
    if observed!=set(files)|{'manifest.json'}:raise ValueError('unexpected or missing release member')
    if manifest['codex_binary_sha256']!=CODEX_SHA256 or digest(files.get('runtime/bin/codex',b''))!=CODEX_SHA256:
        raise ValueError('pinned Codex executable differs')
    if 'runtime/bin/specstory' in files and digest(files['runtime/bin/specstory'])!=SPECSTORY_SHA256:
        raise ValueError('pinned SpecStory executable differs')
    expected_pth=(release+'/vendor/site-packages\n').encode()
    if files.get('runtime/rras-vendor-site-packages.pth')!=expected_pth:raise ValueError('vendor environment binding differs')
    source_files={}
    for name,raw in files.items():
        if name=='runtime/rras-vendor-site-packages.pth':continue
        if name.startswith('engineering/systemd/'):
            raw=raw.replace(release.encode(),b'/opt/rras-engineering/releases/standardized-history-runtime')
        source_files[name]=raw
    payload_sha,_=release_digest(source_files)
    if manifest['payload_sha256']!=payload_sha or release!='/opt/rras-engineering/releases/standardized-history-'+payload_sha[:12]:
        raise ValueError('release content identity differs')
    if render_release(source_files,release)!=files:raise ValueError('rendered release members differ')
    return manifest,files


def _unique_object(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('duplicate manifest key')
        result[key]=value
    return result


def build(source,binary,site,destination,commit,specstory=None):
    source=Path(source).resolve(strict=True);destination=Path(destination)
    if (destination.exists() or destination.is_symlink() or not destination.is_absolute() or
            not re.fullmatch('[0-9a-f]{40}',commit)):
        raise ValueError('new absolute candidate and exact commit required')
    head=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],timeout=10).decode().strip()
    changed=subprocess.check_output(['git','-C',str(source),'status','--porcelain','--untracked-files=all'],timeout=10)
    if head!=commit or changed:raise ValueError('clean exact source commit required')
    files=source_files(source);files.update(site_packages(site));binary_files=binaries(binary,specstory);files.update(binary_files)
    if len(files)>2048 or sum(map(len,files.values()))>1024*1024*1024:raise ValueError('bounded immutable release required')
    content_sha,_=release_digest(files);release='/opt/rras-engineering/releases/standardized-history-'+content_sha[:12]
    rendered=render_release(files,release)
    final_inventory={name:digest(raw) for name,raw in sorted(rendered.items())}
    manifest=dict(contract='rras-codex-runtime-release.v1',source_commit=commit,release=release,
        payload_sha256=content_sha,codex_binary_sha256=CODEX_SHA256,dependencies=DEPENDENCIES,
        installed=False,activated=False,files=final_inventory)
    destination.mkdir(mode=0o700,parents=True)
    for name,raw in rendered.items():
        safe_relative(name);path=destination/name;path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        path.write_bytes(raw);path.chmod(0o555 if name in binary_files else 0o444)
    manifest_raw=json.dumps(manifest,sort_keys=True,indent=2).encode()+b'\n'
    (destination/'manifest.json').write_bytes(manifest_raw);(destination/'manifest.json').chmod(0o444)
    manifest_sha=digest(manifest_raw);verify(destination,manifest_sha)
    return dict(phase='inactive_codex_runtime_release_prepared',release=release,files=len(files),
        manifest_sha256=manifest_sha,source_commit=commit,installed=False,activated=False,
        api_calls=0,models_started=0)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source','binary','site-packages','destination','source-commit'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--specstory',help='optional pinned SpecStory candidate; does not enable collection')
    args=parser.parse_args()
    try:print(json.dumps(build(args.source,args.binary,args.site_packages,args.destination,args.source_commit,args.specstory),sort_keys=True))
    except Exception:parser.exit(1,'Inactive Codex runtime packaging refused; preserve existing releases and state.\n')


if __name__=='__main__':main()
