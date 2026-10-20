"""Root-private independent-validation staging; never execute a repository recipe.

Reconstruct from protected review bundle, not worker/operator mutable Git state.
Leave workspace root-private until a future launcher has acquired the fixed slot.
"""
import hashlib
import importlib.util
import os
from pathlib import Path
import stat
import subprocess

MAX_FILES = 16384
MAX_FILE = 64 * 1024 * 1024
MAX_TOTAL = 256 * 1024 * 1024


def local(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def git(repo, *args):
    env = {'PATH':'/usr/bin:/bin', 'HOME':'/nonexistent', 'LANG':'C.UTF-8',
           'GIT_CONFIG_NOSYSTEM':'1', 'GIT_CONFIG_GLOBAL':'/dev/null', 'GIT_TERMINAL_PROMPT':'0'}
    prefix = ['/usr/bin/git', '-c', 'core.hooksPath=/dev/null', '-c', 'core.fsmonitor=false',
              '-c', 'protocol.allow=never', '-c', 'protocol.file.allow=always']
    if repo is not None: prefix += ['-C', str(repo)]
    return subprocess.run(prefix + list(args), env=env, stdin=subprocess.DEVNULL,
        capture_output=True, check=True, timeout=60).stdout


def inventory(repo, commit):
    """Read trusted bundle objects, refusing unsupported baseline special entries."""
    entries = git(repo, 'ls-tree', '-r', '-z', commit).split(b'\0')
    result = {}; total = 0
    for entry in entries:
        if not entry: continue
        meta, raw_name = entry.split(b'\t', 1); mode, kind, oid = meta.split(b' ')
        name = raw_name.decode('utf-8'); path = Path(name)
        if (mode not in (b'100644', b'100755') or kind != b'blob' or not name or
                path.is_absolute() or str(path) != name or any(p in ('.', '..', '.git') for p in path.parts)):
            raise ValueError('regular canonical validation tree required; special entries unsupported')
        size = int(git(repo, 'cat-file', '-s', oid.decode()))
        total += size
        if size > MAX_FILE or total > MAX_TOTAL or len(result) >= MAX_FILES:
            raise ValueError('validation tree exceeds bound')
        result[name] = {'mode': mode.decode(), 'blob': oid.decode(), 'size': size}
    return result


def filesystem(repo):
    """Hash private staged regular files without trusting an index or Git filters.

    Used only while the entire stage is root-private. This is not a safe reader
    for an active worker checkout; future post-execution capture needs its own
    stopped-identity and protected descriptor/ownership checks.
    """
    result = {}; total = 0
    def walk(directory):
        nonlocal total
        for path in directory.iterdir():
            if path == repo / '.git': continue
            info = path.lstat()
            if stat.S_ISDIR(info.st_mode):
                walk(path); continue
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > MAX_FILE:
                raise ValueError('bounded regular staged file required')
            total += info.st_size
            if total > MAX_TOTAL or len(result) >= MAX_FILES:
                raise ValueError('validation filesystem exceeds bound')
            # Ownership/ancestor checks happen inside the protected reader.
            raw = local('publication_custody').root_bytes(path, MAX_FILE)
            blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
            result[path.relative_to(repo).as_posix()] = {
                'mode': '100755' if info.st_mode & 0o111 else '100644', 'blob': blob, 'size':len(raw)}
    walk(repo)
    return result


def reconstruct(repo, commit, baseline, allowed):
    """Only call on a fresh private clone of a verified protected bundle."""
    if git(repo, 'rev-list', '--parents', '-n', '1', commit).decode().strip().split() != [commit, baseline]:
        raise ValueError('single baseline parent review commit required')
    expected = inventory(repo, commit); before = inventory(repo, baseline)
    changed = {name for name in set(expected) | set(before) if expected.get(name) != before.get(name)}
    if not changed or not changed <= set(allowed):
        raise ValueError('validation tree changes exceed exact admitted paths')
    git(repo, 'checkout', '--quiet', '--detach', commit)
    git(repo, 'reset', '--quiet', '--mixed', baseline)
    for name in sorted(set(expected) - set(before)):
        git(repo, '--literal-pathspecs', 'add', '--intent-to-add', '--force', '--', name)
    if filesystem(repo) != expected:
        raise ValueError('reconstructed worktree differs from exact review tree')
    return expected


def administrator():
    if os.geteuid() != 0: raise ValueError('administrator staging required')
    local('approved_launch').trusted(Path(__file__))


def stage(finish_custody, package, destination):
    administrator()
    f = local('workflow_finish'); p = local('workflow_publication'); a = local('activity')
    finish, review, members = f.load(finish_custody)
    handoff_raw, handoff = p.handoff(package, finish, review, members)
    prepared = handoff['prepared']
    contract = local('post_validation').plan(review, prepared, a.digest(a.encoded(finish)))
    root = Path(destination)
    if not root.is_absolute() or root.resolve() != root:
        raise ValueError('absolute canonical staging destination required')
    local('approved_launch').trusted(root.parent)
    if root.exists() or root.is_symlink(): raise ValueError('fresh validation stage required')
    data = local('publication_custody').root_bytes(Path(package) / 'review.bundle', local('publication_handoff').LIMIT)
    if a.digest(data) != handoff['bundle_sha256'] or len(data) != handoff['bundle_size']:
        raise ValueError('review bundle changed')
    root.mkdir(mode=0o700); a.fsync_directory(root.parent)
    # Any failure preserves partial private stage; it is never reused automatically.
    a.absent(root / 'review.bundle', data)
    a.absent(root / 'handoff.json', handoff_raw)
    repo = root / 'repo'
    git(None, 'clone', '--quiet', '--no-checkout', '--no-hardlinks', str(root / 'review.bundle'), str(repo))
    git(repo, 'remote', 'remove', 'origin')
    commit = prepared['commit']; baseline = prepared['baseline']
    expected = reconstruct(repo, commit, baseline, review['request']['allowed_paths'])
    record = dict(schema_version=1, plan=contract, handoff_sha256=a.digest(handoff_raw),
        bundle_sha256=handoff['bundle_sha256'], review_tree=git(repo, 'rev-parse', commit + '^{tree}').decode().strip(),
        baseline_head=baseline, files=expected,
        index_sha256=a.digest(local('publication_custody').root_bytes(repo / '.git/index', 8*1024*1024)),
        config_sha256=a.digest(local('publication_custody').root_bytes(repo / '.git/config', 1024*1024)),
        staged_for_execution=False,
        worker_access_granted=False, publication_authorized=False)
    a.absent(root / 'validation-stage.json', a.encoded(record))
    return {'staged':True, 'commit':commit, 'files':len(expected), 'worker_access_granted':False,
            'service_started':False, 'publication_authorized':False}


def verify(finish_custody, package, destination):
    """Recheck protected stage before any future launch; never read worker state."""
    administrator(); root = Path(destination); a = local('activity')
    local('approved_launch').trusted(root)
    if not root.is_absolute() or stat.S_IMODE(root.stat().st_mode) != 0o700:
        raise ValueError('private protected stage required')
    read = local('publication_custody').root_bytes
    receipt = local('workflow_journal').decode(read(root / 'validation-stage.json', 8*1024*1024))
    finish, review, members = local('workflow_finish').load(finish_custody)
    raw, handoff = local('workflow_publication').handoff(package, finish, review, members)
    contract = local('post_validation').plan(review, handoff['prepared'], a.digest(a.encoded(finish)))
    if (receipt['schema_version'] != 1 or receipt['plan'] != contract or
            receipt['worker_access_granted'] is not False or receipt['staged_for_execution'] is not False or
            receipt['publication_authorized'] is not False or
            receipt['handoff_sha256'] != a.digest(raw) or read(root / 'handoff.json', 1024*1024) != raw or
            receipt['bundle_sha256'] != handoff['bundle_sha256'] or
            a.digest(read(root / 'review.bundle', local('publication_handoff').LIMIT)) != handoff['bundle_sha256']):
        raise ValueError('validation stage custody changed')
    repo = root / 'repo'; local('approved_launch').trusted(repo / '.git' / 'config')
    if (a.digest(read(repo / '.git/index', 8*1024*1024)) != receipt['index_sha256'] or
            a.digest(read(repo / '.git/config', 1024*1024)) != receipt['config_sha256']):
        raise ValueError('validation index/configuration changed')
    commit = contract['identity']['commit']; baseline = contract['identity']['baseline']
    if (git(repo, 'rev-parse', 'HEAD').decode().strip() != baseline or receipt['baseline_head'] != baseline or
            git(repo, 'rev-parse', commit + '^{tree}').decode().strip() != receipt['review_tree'] or
            git(repo, 'rev-list', '--parents', '-n', '1', commit).decode().strip().split() != [commit, baseline] or
            inventory(repo, commit) != receipt['files'] or filesystem(repo) != receipt['files']):
        raise ValueError('validation stage content changed')
    return receipt
