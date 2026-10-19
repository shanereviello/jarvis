"""Prepare repository-independent admission snapshots. Never approve or execute.

Inputs are operator-selected records, not authenticated registrations. Installing
or consuming a snapshot at a privileged boundary requires separate trusted capture.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import re


def local(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def beneath(path, root):
    return root == '.' or path == root or path.startswith(root + '/')


def compile_snapshot(registration, work, hermes_project):
    """Translate an exact registration/work pair to existing executor formats.

    No filesystem inspection or authority is implied. Path lists remain exact file
    names, never globs or recursive directory grants. Revision ancestry belongs to
    the history store; this function checks the two selected snapshots only.
    """
    a, records = local('activity'), local('workflow_records')
    records.validate_record(registration)
    records.validate_record(work)
    if registration['kind'] != 'repository_registration' or work['kind'] != 'work_item':
        raise ValueError('registration and work item required')
    a.identifier(hermes_project)
    if (work['repository_id'] != registration['repository_id'] or
            work['registration_sha256'] != records.record_digest(registration)):
        raise ValueError('work must reference the exact registration')
    if work['mode'] != 'approval_driven':
        raise ValueError('managed preparation requires approval-driven work')
    if registration['source']['object_format'] != 'sha1':
        raise ValueError('current managed executor supports SHA-1 Git repositories only')
    baseline = work['baseline']
    if (baseline is None or baseline['ref'] not in registration['baseline_refs'] or
            not re.fullmatch(r'refs/(heads|remotes/origin)/[A-Za-z0-9][A-Za-z0-9_/-]{0,120}', baseline['ref']) or
            not re.fullmatch('[0-9a-f]{40}', baseline['commit'])):
        raise ValueError('admitted named baseline and exact commit required')
    paths = work['requested_paths']
    policy = registration['path_policy']
    for path in paths:
        if (not any(beneath(path, root) for root in policy['allowed_roots']) or
                any(beneath(path, root) or beneath(root, path) for root in policy['denied_roots']) or
                any(part in {'.git', '.aws', '.codex'} for part in Path(path).parts) or
                Path(path).name in {'AGENTS.md', 'RRAS_TASK.md'}):
            raise ValueError('requested file is outside the admitted scope')
    recipes = [r for r in registration['validation_recipes'] if r['validation_id'] == work['validation_id']]
    if len(recipes) != 1:
        raise ValueError('one registered validation recipe required')
    recipe = recipes[0]
    request = dict(schema_version=1, task_id=work['work_item_id'] + '-r' + str(work['revision']),
                   repository_id=work['repository_id'], objective=work['objective'],
                   allowed_paths=paths, validation_argv=recipe['argv'], worker_timeout_seconds=300,
                   validation_timeout_seconds=recipe['timeout_seconds'], commit_policy='leave_uncommitted')
    local('task_contract').validate_request(request)
    repo_id = work['repository_id']
    # Same shapes used by intake/capture/runner. These are inert candidate files,
    # never an enrollment, approval, publication grant or privileged installation.
    legacy_policy = {'schema_version': 1, 'identities': {'hermes': [repo_id]},
                     'repositories': {repo_id: {'enabled': True, 'allowed_paths': paths,
                         'validations': {recipe['validation_id']: recipe['argv']},
                         'worker_timeout_seconds': 300,
                         'validation_timeout_seconds': recipe['timeout_seconds']}}}
    registry = {'schema_version': 1, 'repositories': [{'repository_id': repo_id,
                'path': registration['source']['canonical_path'], 'enabled': True,
                'hermes_project': hermes_project}]}
    return {'schema_version': 1, 'kind': 'admission_candidate',
            'registration_sha256': records.record_digest(registration),
            'work_item_sha256': records.record_digest(work), 'registration': registration,
            'work_item': work, 'request': request, 'policy': legacy_policy, 'registry': registry,
            'execution_authorized': False, 'publication_authorized': False}


def inspect_repository(snapshot):
    """Read-only baseline preflight; a later trusted capture must repeat it."""
    a = local('activity')
    registration, work = snapshot['registration'], snapshot['work_item']
    path = registration['source']['canonical_path']
    if str(a.canonical_repo(path)) != path:
        raise ValueError('canonical repository path changed')
    root = Path(path)
    if a.git(root, 'rev-parse', '--show-object-format').decode().strip() != registration['source']['object_format']:
        raise ValueError('Git object format mismatch')
    if a.git(root, 'status', '--porcelain', '--untracked-files=all').strip():
        raise ValueError('clean canonical repository required')
    baseline = work['baseline']
    commit = a.git(root, 'rev-parse', '--verify', '--end-of-options', baseline['ref'] + '^{commit}').decode().strip()
    if commit != baseline['commit']:
        raise ValueError('baseline moved; prepare a revised work item')
    for name in work['requested_paths']:
        item = root / name
        for parent in (item, *item.parents):
            if parent == root:
                break
            if parent.is_symlink():
                raise ValueError('requested path traverses a symlink')
        if item.is_dir():
            raise ValueError('exact file paths required, not directories')
        # HEAD may differ from the selected named baseline. Inspect its tree too,
        # including ancestors, so an older symlink/gitlink cannot bypass preflight.
        for prefix in [str(p) for p in reversed(Path(name).parents) if str(p) != '.'] + [name]:
            entry = a.git(root, 'ls-tree', commit, '--', ':(literal)' + prefix)
            if entry and entry.split(b' ', 1)[0] in {b'120000', b'160000'}:
                raise ValueError('baseline path traverses a symlink or submodule')
        entry = a.git(root, 'ls-tree', commit, '--', ':(literal)' + name)
        if entry.startswith(b'040000 '):
            raise ValueError('baseline path is a directory')
    return {'baseline_verified': True, 'api_calls': 0}


def prepare(registration_path, work_path, hermes_project, state):
    a = local('activity')
    snapshot = compile_snapshot(a.load(registration_path), a.load(work_path), hermes_project)
    inspect_repository(snapshot)
    raw = a.encoded(snapshot)
    candidate_id = a.digest(raw)
    root = a.private_dir(state)
    a.absent(root / (candidate_id + '.admission.json'), raw)
    return {'candidate_id': candidate_id, 'status': 'pending_trusted_capture',
            'execution_authorized': False, 'publication_authorized': False, 'api_calls': 0}


def read_candidate(state, candidate_id):
    a = local('activity')
    if not re.fullmatch('[0-9a-f]{64}', candidate_id):
        raise ValueError('exact candidate digest required')
    snapshot = a.load(Path(state) / (candidate_id + '.admission.json'))
    if a.digest(a.encoded(snapshot)) != candidate_id:
        raise ValueError('candidate changed')
    project = snapshot['registry']['repositories'][0]['hermes_project']
    expected = compile_snapshot(snapshot['registration'], snapshot['work_item'], project)
    if a.encoded(snapshot) != a.encoded(expected):
        raise ValueError('candidate translation inconsistent')
    inspect_repository(snapshot)
    return {'candidate_id': candidate_id, 'repository_id': snapshot['work_item']['repository_id'],
            'work_item_id': snapshot['work_item']['work_item_id'],
            'registration_sha256': snapshot['registration_sha256'],
            'work_item_sha256': snapshot['work_item_sha256'],
            'baseline': snapshot['work_item']['baseline'],
            'status': 'pending_trusted_capture', 'execution_authorized': False,
            'publication_authorized': False, 'api_calls': 0}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    commands = p.add_subparsers(dest='command', required=True)
    prep = commands.add_parser('prepare')
    for name in ('registration', 'work-item', 'hermes-project', 'state'):
        prep.add_argument('--' + name, required=True)
    read = commands.add_parser('inspect')
    for name in ('state', 'candidate-id'):
        read.add_argument('--' + name, required=True)
    args = p.parse_args(argv)
    try:
        if args.command == 'prepare':
            result = prepare(args.registration, args.work_item, args.hermes_project, args.state)
        else:
            result = read_candidate(args.state, args.candidate_id)
    except (ValueError, OSError, KeyError, TypeError):
        # Do not echo objectives, raw Git errors, configuration or private paths.
        p.exit(1, 'Admission refused; review input records and repository baseline.\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
