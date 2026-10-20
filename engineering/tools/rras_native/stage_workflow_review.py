"""Root inactive workflow staging/preflight. Never activates/restarts production.

Verify an exact manifest and approved source ancestry, stage new protected code,
save private rollback previews, and exercise only synthetic projection publication.
No real journal/config/approval creation, provider key, model, unit or live writes.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False) + '\n').encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def protected(path):
    path = Path(path)
    if not path.is_absolute():
        raise ValueError('absolute root-protected path required')
    for item in (path, *path.parents):
        info = item.lstat()
        if stat.S_ISLNK(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError('unprotected administrator path')
    return path


def command(argv, **kwargs):
    return subprocess.run(argv, env={'PATH': '/usr/bin:/bin', 'HOME': '/nonexistent', 'LANG': 'C.UTF-8'},
                          capture_output=True, check=True, timeout=60, **kwargs)


def write(path, data, mode=0o600):
    with path.open('xb') as stream:
        os.fchmod(stream.fileno(), mode)
        stream.write(data); stream.flush(); os.fsync(stream.fileno())


def sync(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)


def stage(candidate, expected):
    if os.getuid() != 0 or os.geteuid() != 0:
        raise ValueError('administrator invocation required')
    if not re.fullmatch('[0-9a-f]{64}', expected):
        raise ValueError('exact manifest digest required')
    candidate = Path(candidate)
    if not candidate.is_absolute() or candidate.resolve(strict=True) != candidate:
        raise ValueError('non-symlink absolute candidate required')
    manifest_path = candidate / 'release-manifest.json'
    raw = manifest_path.read_bytes()
    if manifest_path.is_symlink() or len(raw) > 1024 * 1024 or sha(raw) != expected:
        raise ValueError('manifest changed')
    manifest = json.loads(raw)
    if manifest['kind'] != 'workflow_production_candidate' or manifest['schema_version'] != 1 or not re.fullmatch('workflow-[0-9a-f]{12}', manifest['release_id']):
        raise ValueError('invalid production manifest')
    commit = manifest['source_commit']
    if not re.fullmatch('[0-9a-f]{40}', commit):
        raise ValueError('exact source commit required')
    command(['/usr/bin/git', '-c', 'safe.directory=/srv/git/jarvis', '-c', 'core.hooksPath=/dev/null',
             '-C', '/srv/git/jarvis', 'merge-base', '--is-ancestor', commit, 'main'])
    if not 1 <= len(manifest['files']) <= 512:
        raise ValueError('bounded package required')
    payload = {}
    for name, digest in manifest['files'].items():
        relative = PurePosixPath(name)
        path = candidate / name
        if (relative.is_absolute() or '..' in relative.parts or str(relative) != name or
                not name.startswith(('engineering/', 'vendor/', 'config/', 'entrypoints/')) or
                path.is_symlink() or path.resolve(strict=True) != path or path.stat().st_size > 4 * 1024 * 1024):
            raise ValueError('invalid package member')
        data = path.read_bytes()
        if sha(data) != digest:
            raise ValueError('package member changed')
        payload[name] = data
    if sum(map(len, payload.values())) > 16 * 1024 * 1024:
        raise ValueError('oversized package')
    identity = {key: manifest[key] for key in ('source_commit', 'files', 'dependencies')}
    if 'workflow-' + sha(encoded(identity))[:12] != manifest['release_id']:
        raise ValueError('release identity mismatch')
    plan_raw = (candidate / 'install-plan.json').read_bytes()
    if (candidate / 'install-plan.json').is_symlink() or sha(plan_raw) != manifest['plan_sha256']:
        raise ValueError('plan changed')
    plan = json.loads(plan_raw)
    release = Path('/opt/rras-engineering/releases') / manifest['release_id']
    if plan['release'] != str(release) or plan['activation_authorized'] is not False or not plan['journal_required']:
        raise ValueError('inactive journal-required plan required')
    parent = Path('/var/lib/rras-workflow-installations')
    protected(release.parent); protected(parent.parent)
    if not parent.exists():
        parent.mkdir(mode=0o700); sync(parent.parent)
    protected(parent)
    if stat.S_IMODE(parent.stat().st_mode) != 0o700:
        raise ValueError('private installation journal parent required')
    journal = parent / manifest['release_id']
    fixture = Path('/var/lib/rras-workflow-publication-acceptance-' + manifest['release_id'][9:])
    for path in (release, journal, fixture):
        if path.exists() or path.is_symlink():
            raise ValueError('staging roots already exist; preserve and inspect, never adopt')
    # Complete current-state checks before creating any release content.
    for field, digest_key in (('profile', 'profile_sha256'), ('codex_config', 'codex_config_sha256')):
        path = protected(plan['operator_config'][field])
        if sha(path.read_bytes()) != plan[digest_key]:
            raise ValueError('existing pinned session configuration changed')
    python = Path('/opt/rras-engineering/releases/native-10/venv/bin/python')
    protected(python.resolve(strict=True))
    config_path = Path('/srv/hermes/data/config.yaml')
    if config_path.resolve(strict=True) != config_path or not config_path.is_file() or config_path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError('regular non-symlink Hermes configuration required')
    original = config_path.read_bytes()
    if sha(original) != plan['hermes']['expected_config_sha256']:
        raise ValueError('Hermes configuration changed; refresh review')
    current = json.loads(command(['/usr/bin/docker', 'inspect', 'hermes']).stdout)[0]
    if current['Image'] != plan['hermes']['image'] or not current['State']['Running']:
        raise ValueError('Hermes identity/running state changed')
    targets = {row['Destination']: (row['Source'], row['RW'], row['Type']) for row in current['Mounts']}
    expected_targets = {'/opt/data': ('/srv/hermes/data', True, 'bind'),
                        '/workspace/git/jarvis': ('/srv/git/jarvis', False, 'bind'),
                        '/workspace/git/robot_ws': ('/srv/git/robot_ws', False, 'bind'),
                        '/workspace/jarvis-artifacts': ('/srv/notes/jarvis-artifacts', True, 'bind'),
                        '/workspace/shared': ('/srv/shared/jarvis', True, 'bind')}
    if targets != expected_targets:
        raise ValueError('Hermes mounts changed')
    compose = protected(plan['hermes']['compose'])
    compose_raw = compose.read_bytes()
    # Transform private YAML only in the existing container's pinned parser.
    # Its stdout is captured to the root-private journal, never printed to user.
    transform = '''import json,sys,yaml
p=json.load(sys.stdin);d=yaml.safe_load(p['original']);expected={'hindsight','jarvis-engineering','linear','linear-actions','rras-coding-preparation','todoist'}
assert set(d['mcp_servers'])==expected
assert p['name'] not in d['mcp_servers']
d['mcp_servers'][p['name']]=p['entry']
raw=yaml.safe_dump(d,sort_keys=False);assert yaml.safe_load(raw)==d
sys.stdout.write(raw)
'''
    request = encoded({'original': original.decode(), 'name': plan['hermes']['new_entry_name'], 'entry': plan['hermes']['new_entry']})
    transformed = command(['/usr/bin/docker', 'exec', '-i', '--user', '1000:1000', 'hermes',
                           '/opt/hermes/.venv/bin/python', '-I', '-B', '-c', transform], input=request).stdout
    journal.mkdir(mode=0o700)
    write(journal / 'config.original', original)
    write(journal / 'config.candidate', transformed)
    write(journal / 'compose.original', compose_raw)
    write(journal / 'container.original.json', encoded(current))
    write(journal / 'install-plan.json', plan_raw)
    write(journal / 'release-manifest.json', raw)
    overlay = {'services': {'hermes': {'volumes': [
        {'type': 'bind', 'source': row['source'], 'target': row['target'], 'read_only': True}
        for row in plan['hermes']['add_readonly_mounts']]}}}
    write(journal / 'compose.override.json', encoded(overlay))
    release.mkdir(mode=0o755)
    for name, data in payload.items():
        destination = release / name
        destination.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
        write(destination, data, 0o644)
    write(release / 'release-manifest.json', raw, 0o444)
    for directory in sorted({release, *[p.parent for p in release.rglob('*')]}, key=lambda p: len(p.parts), reverse=True):
        os.chmod(directory, 0o755); sync(directory)
    # A private fixture, never the planned production journal or history tree.
    fixture.mkdir(mode=0o755)
    os.chmod(fixture, 0o755)
    (fixture / 'store').mkdir(mode=0o700)
    (fixture / 'views').mkdir(mode=0o750)
    os.chown(fixture / 'views', 0, 1000)
    os.chmod(fixture / 'views', 0o750)
    exercise = '''import importlib.util,json,sys
from pathlib import Path
base=Path(sys.argv[1]);root=Path(sys.argv[2]);sys.path.insert(0,str(base/'vendor'))
def local(name):
 s=importlib.util.spec_from_file_location(name,base/'engineering/tools/rras_native'/(name+'.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
j=local('workflow_journal');a=local('activity');registration=json.loads((base/'config/jarvis-registration.json').read_bytes())
actor={'type':'service','id':'publication-acceptance'};provenance={'kind':'imported','source':{'namespace':'external','id':'synthetic-publication-acceptance'},'source_sha256':None,'recorded_by':actor}
work={'schema_version':1,'kind':'work_item','work_item_id':'wrk_'+'7'*32,'revision':1,'supersedes_sha256':None,'repository_id':'jarvis','registration_sha256':a.digest(a.encoded(registration)),'created_at':'2026-10-19T12:00:00Z','actor':actor,'provenance':provenance,'mode':'interactive','objective':'PRIVATE_FIXTURE_ONLY','requested_paths':[],'validation_id':None,'baseline':None,'references':[]}
store=j.Journal(root/'store',create=True);store.append([registration,work]);result=local('publish_workflow_views').publish(root/'store',root/'views',1000)
assert result['work_items']==1 and result['pages']==1
assert b'PRIVATE_FIXTURE_ONLY' not in (root/'views/index.json').read_bytes()
for p in (root/'views').glob('g*.json'):assert b'PRIVATE_FIXTURE_ONLY' not in p.read_bytes()
print(json.dumps(result))
'''
    published = json.loads(command([str(python), '-I', '-B', '-c', exercise, str(release), str(fixture)]).stdout)
    permissions = '''import json,sys
from pathlib import Path
store,views=map(Path,sys.argv[1:]);index=json.loads((views/'index.json').read_bytes());assert len(index['pages'])==1
json.loads((views/index['pages'][0]['file']).read_bytes())
try:(store/'workflow.sqlite3').read_bytes()
except PermissionError:pass
else:raise AssertionError('private database readable')
try:(views/'index.json').open('ab')
except PermissionError:pass
else:raise AssertionError('published index writable')
print('role_permissions_verified')
'''
    command(['/usr/bin/setpriv', '--reuid=1000', '--regid=1000', '--clear-groups', '--no-new-privs',
             str(python), '-I', '-B', '-c', permissions, str(fixture / 'store'), str(fixture / 'views')])
    after = json.loads(command(['/usr/bin/docker', 'inspect', 'hermes']).stdout)[0]
    if (after['Id'], after['State']['StartedAt'], after['RestartCount']) != (current['Id'], current['State']['StartedAt'], current['RestartCount']) or config_path.read_bytes() != original:
        raise ValueError('production identity/config changed during inactive preflight')
    answer = {'phase': 'inactive_workflow_release_staged', 'release': str(release), 'journal': str(journal),
              'manifest_sha256': expected, 'source_commit': commit, 'hermes_container': current['Id'],
              'original_config_sha256': sha(original), 'candidate_config_sha256': sha(transformed),
              'original_compose_sha256': sha(compose_raw), 'publisher_fixture': str(fixture),
              'publisher_pages': published['pages'], 'reader_permissions_verified': True,
              'production_journal_created': False, 'production_configuration_changed': False,
              'hermes_restarted': False, 'activation_authorized': False, 'api_calls': 0}
    write(journal / 'preflight-result.json', encoded(answer)); sync(journal); sync(release.parent)
    return answer


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidate', required=True)
    p.add_argument('--manifest-sha256', required=True)
    args = p.parse_args(argv)
    print(json.dumps(stage(args.candidate, args.manifest_sha256), indent=2))


if __name__ == '__main__':
    main()
