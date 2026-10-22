"""Root model-free acceptance using exact fake worker, sentinel and isolated unit.

Never invoke from a live release: manual_runner.py must equal FAKE_WORKER. Roots
must be new. No provider credentials, production unit changes or model session.
"""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor


def local(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module



def fixture_records(here, repo, commit, repository_id):
    a = local('activity')
    registration, work = json.loads((here / 'library-managed.json').read_text())[:2]
    if repository_id not in ('example_library', 'closeout_library_two'):
        raise ValueError('known offline repository fixture required')
    registration.update(repository_id=repository_id, registration_id='reg_' + a.digest(repository_id.encode())[:32])
    work.update(repository_id=repository_id, work_item_id='wrk_' + a.digest(repository_id.encode())[:32])
    registration['source']['canonical_path'] = str(repo)
    registration['path_policy']['allowed_roots'] = ['.']
    registration['validation_recipes'] = [{'validation_id': 'fixture', 'argv': ['/usr/bin/true'], 'execution_identity': 'engineering_worker', 'timeout_seconds': 10}]
    work.update(registration_sha256=a.digest(a.encoded(registration)), objective='Offline acceptance fixture for ' + repository_id + ' only.',
                requested_paths=['value.py'], validation_id='fixture', baseline={'ref': 'refs/heads/main', 'commit': commit})
    return registration, work


def run(root, repository_id='example_library'):
    if os.getuid() != 0 or os.geteuid() != 0:
        raise ValueError('root acceptance required')
    root = Path(root)
    here = Path(__file__).parent
    fixture = local('probe_approved_launch')
    if (here / 'manual_runner.py').read_text() != fixture.FAKE_WORKER:
        raise ValueError('exact model-free worker required')
    launcher, operator, events = local('approved_launch'), local('operator_control'), local('managed_events')
    a, journal = local('activity'), local('workflow_journal')
    launcher.trusted(here)
    launcher.slot()  # Production slot/UID must be idle; never adopt or stop it.
    if root.exists() or root.is_symlink() or not root.is_absolute():
        raise ValueError('fresh absolute acceptance root required')
    root.mkdir(mode=0o755)
    for name, mode in (('control', 0o700), ('jobs', 0o755), ('workers', 0o700), ('journal', 0o700), ('views', 0o700)):
        (root / name).mkdir(mode=mode)
    os.chown(root / 'workers', 996, 996)
    state = root / 'control'
    approvals = state / 'approvals'
    approvals.mkdir(mode=0o700)
    store = journal.Journal(root / 'journal', create=True)
    repo = state / 'canonical'
    repo.mkdir(mode=0o700)
    def git(*args):
        return subprocess.run(['/usr/bin/git', '-C', str(repo), *args], check=True, capture_output=True).stdout
    git('init', '-q', '-b', 'main')
    (repo / 'value.py').write_text('value=0\n')
    git('add', '.')
    git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', '-c', 'commit.gpgsign=false', 'commit', '-qm', 'fixture')
    commit = git('rev-parse', 'HEAD').decode().strip()
    registration, work = fixture_records(here, repo, commit, repository_id)
    registration_path, work_path = state / 'registration.json', state / 'work.json'
    a.absent(registration_path, a.encoded(registration))
    a.absent(work_path, a.encoded(work))
    profile, codex = here / 'profile.json', here / 'codex-config.toml'
    config = state / 'operator.json'
    config_bytes = a.encoded({'schema_version': 1, 'registration': registration, 'hermes_project': 'offline-fixture',
                             'profile': str(profile), 'codex_config': str(codex), 'journal': str(root / 'journal')})
    a.absent(config, config_bytes)
    proposals = state / 'proposals'
    prepared = local('repository_admission').prepare(registration_path, work_path, 'offline-fixture', proposals)
    # Bind only the synthetic launcher/unit. Permission checks, code/config hashes,
    # journal, clone, one-use approval, account checks and systemd are real.
    launcher.UNIT = 'rras-workflow-acceptance-' + a.digest(str(root).encode())[:12] + '.service'
    original_operator_local, original_launcher_local, original_event_local = operator.local, launcher.local, events.local
    operator.local = lambda name: launcher if name == 'approved_launch' else events if name == 'managed_events' else original_operator_local(name)
    launcher.local = lambda name: operator if name == 'operator_control' else events if name == 'managed_events' else original_launcher_local(name)
    events.local = lambda name: operator if name == 'operator_control' else original_event_local(name)
    original_argv = launcher.argv
    def offline_argv(*args):
        argv = original_argv(*args)
        index = argv.index('/usr/bin/env')
        return argv[:index] + ['-p', 'PrivateNetwork=yes', '-p', 'RestrictAddressFamilies=AF_UNIX'] + argv[index:]
    launcher.argv = offline_argv
    captured = operator.capture(config, proposals, prepared['candidate_id'], approvals, 'codex/offline-fixture')
    first = operator.approve(approvals, captured['review_id'], config, approve_one_execution=True)
    second = operator.approve(approvals, captured['review_id'], config, approve_one_execution=True)
    key = state / 'sentinel'
    a.absent(key, fixture.SENTINEL.encode())
    def invoke(authorization):
        return operator.launch(approvals, authorization, config, root / 'jobs', root / 'workers', key)
    ready = busy = False
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(invoke, first['authorization_id'])
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and not future.done():
            ready = bool(list((root / 'workers').glob('approved-*/work/fake-ready.json')))
            if ready: break
            time.sleep(.05)
        if ready:
            try: invoke(second['authorization_id'])
            except ValueError: busy = True
        result = future.result(timeout=430)
    if not ready or not busy or result['service_exit'] != 0 or result['host_stop_verified'] is not True:
        raise ValueError('offline service acceptance failed; retain all state')
    if (approvals / (second['authorization_id'] + '.consumed.json')).exists():
        raise ValueError('busy slot consumed second approval')
    replay = False
    try: invoke(first['authorization_id'])
    except FileExistsError: replay = True
    if not replay: raise ValueError('authorization replay accepted')
    before = len(store.records())
    operator.reconcile(approvals, first['authorization_id'])
    if len(store.records()) != before:
        raise ValueError('receipt replay duplicated journal records')
    config.write_bytes(config_bytes + b' ')
    revoked = False
    try: invoke(second['authorization_id'])
    except ValueError: revoked = True
    config.write_bytes(config_bytes)
    a.fsync_directory(state)
    if not revoked or (approvals / (second['authorization_id'] + '.consumed.json')).exists():
        raise ValueError('configuration revocation failed')
    projection = root / 'views' / 'work.json'
    store.publish_jarvis(projection, work['work_item_id'])
    os.chown(root / 'views', 0, 1000)
    os.chmod(root / 'views', 0o750)
    os.chown(projection, 0, 1000)
    permissions = '''import json,sys
from pathlib import Path
for value in sys.argv[1:3]:
 try: Path(value).read_bytes()
 except PermissionError: pass
 else: raise AssertionError('private data readable')
if len(sys.argv)>3:
 p=Path(sys.argv[3]);json.loads(p.read_bytes())
 try: p.open('ab')
 except PermissionError: pass
 else: raise AssertionError('projection writable')
print('permission_boundary_verified')
'''
    python = str(launcher.RELEASE / 'venv/bin/python')
    for uid in (996, 1000):
        args = ['/usr/bin/setpriv', '--reuid=' + str(uid), '--regid=' + str(uid), '--clear-groups', '--no-new-privs',
                python, '-I', '-B', '-c', permissions, str(root / 'journal/workflow.sqlite3'), str(approvals / (first['authorization_id'] + '.approval.json'))]
        if uid == 1000: args.append(str(projection))
        subprocess.run(args, check=True, capture_output=True, timeout=15)
    reopened = journal.Journal(root / 'journal')
    if len(reopened.outbox()['pending']) != len(reopened.records()):
        raise ValueError('pending index entries lost')
    if reopened.status()['work_items'][0]['attempts'][0]['state'] != 'unfinished':
        raise ValueError('fake service mislabeled as task success')
    launcher.slot()  # Isolated slot gone and UID idle after the fake worker.
    answer = {'phase': 'offline_workflow_host_verified', 'api_calls': 0, 'worker_uid': 996,
              'real_credentials_used': False, 'production_unit_used': False, 'unit': launcher.UNIT,
              'root': str(root), 'repository_id': repository_id, 'private_network': True, 'records': len(reopened.records()),
              'cases': ['protected_capture', 'journal_approval', 'sentinel_delivery', 'uid996_fake_worker',
                        'slot_exclusion', 'busy_approval_preserved', 'host_stop', 'replay_refused',
                        'journal_reconciliation_idempotent', 'configuration_revocation',
                        'private_journal_denied_996_and_1000', 'projection_read_only_for_1000',
                        'outbox_restart_retained', 'task_success_not_inferred']}
    a.absent(state / 'acceptance-result.json', a.encoded(answer))
    return answer


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    parser.add_argument('--repository-id', choices=('example_library', 'closeout_library_two'), default='example_library')
    args = parser.parse_args()
    print(json.dumps(run(args.root, args.repository_id)))
