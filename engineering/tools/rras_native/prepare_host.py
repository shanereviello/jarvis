"""Prepare a credential-free host review bundle; never install or launch it."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

REVISION = '76952ba54f5dd83f4f5bd0246059171b4b9d1c4a'
PINS = {'pyproject.toml': '1f928b1560b0669291b3f7d562aa78c99ac4f927375939ca97fd3c3e7494cb91',
        'uv.lock': '8fd868b9da8b6bc2f4aa94a845e210eccdd5e31be7a0b404f0a8527ced0fddec',
        'agent/transports/codex_app_server.py': '1bd7e181aa18e7a1417708ed8b691f3523657096d4fae51a268d8fa6d7afca57'}


def git(source, *args):
    return subprocess.check_output(['git', '-C', str(source), *args], timeout=120)


def verify_source(source):
    if git(source, 'rev-parse', 'HEAD').decode().strip() != REVISION:
        raise ValueError('Hermes commit differs from reviewed revision')
    for name, pin in PINS.items():
        if hashlib.sha256(git(source, 'show', REVISION + ':' + name)).hexdigest() != pin:
            raise ValueError('Hermes source pin mismatch: ' + name)


def prepare(destination, source, binary, model, uv=None):
    source, destination = Path(source), Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError('review destination must be absent')
    verify_source(source)
    if uv is not None and hashlib.sha256(Path(uv).read_bytes()).hexdigest()!='abdc39eab8b4ad341dca91f3823a23a343fae94bdb22ebdd9e91694415206f2f':
        raise ValueError('uv client differs from reviewed pin')
    spec = importlib.util.spec_from_file_location('runtime', Path(__file__).with_name('package_host_runtime.py'))
    runtime = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runtime)
    runtime.prepare(destination, model, binary)
    # Archive committed bytes, never a possibly dirty checkout or live container/home.
    archive = git(source, 'archive', '--format=tar.gz', REVISION)
    (destination / 'hermes-source.tar.gz').write_bytes(archive)
    for name in PINS:
        if '/' not in name:
            (destination / name).write_bytes(git(source, 'show', REVISION + ':' + name))
    (destination / 'manifest.json').unlink()
    config_path = destination / 'profile/config.yaml'
    config = json.loads(config_path.read_text())
    config['kanban'] = {'max_in_progress': 1, 'max_in_progress_per_profile': 1, 'max_spawn': 1,
                        'dispatch_in_gateway': False}
    config_path.write_text(json.dumps(config, indent=2) + '\n')
    plan = {'schema_version': 1, 'status': 'host-source-review-only', 'installed': False,
            'source_repository': 'https://github.com/NousResearch/hermes-agent',
            'hermes_revision': REVISION, 'source_pins': PINS,
            'hermes_archive_sha256': hashlib.sha256(archive).hexdigest(),
            'python_candidate': '3.13.16', 'dependency_lock_included': True,
            'dependency_environment_built': False, 'uv_client_pin': '0.12.23',
            'uv_observed_binary_sha256': 'abdc39eab8b4ad341dca91f3823a23a343fae94bdb22ebdd9e91694415206f2f',
            'account': 'jarvis-codex-engineering', 'account_provisioned': False,
            'release_root': '/opt/rras-engineering', 'state_root': '/var/lib/rras-engineering',
            'launch_environment': {'HOME': '/var/lib/rras-engineering',
              'HERMES_HOME': '/var/lib/rras-engineering', 'CODEX_HOME': '/var/lib/rras-engineering/codex',
              'HERMES_KANBAN_WORKSPACES_ROOT': '/var/lib/rras-engineering/workspaces'},
            'credentials_included': False, 'api_calls': 0, 'budget_policy': 'operator-api-portal',
            'native_dispatch_candidate': ['hermes', 'kanban', 'dispatch', '--max', '1', '--json'],
            'dispatcher_runtime_validated': False, 'continuous_dispatcher_selected': False,
            'gates': ['pin and build frozen core dependencies', 'actual dedicated-UID sandbox acceptance',
                      'native dispatcher child lifetime and approvals', 'review installation and canary']}
    (destination / 'activation-plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    if uv is not None:
        (destination/'build-tools').mkdir(mode=0o700)
        shutil.copyfile(uv,destination/'build-tools/uv')
        (destination/'build-tools/uv').chmod(0o555)
    for name in ('acceptance.py', 'probe_manual_runner.py', 'probe_instruction_handoff.py', 'probe_session_policy.py', 'probe_live_session.py', 'probe_git_metadata.py', 'probe_cli_credentials.py', 'probe_wait_worker.py', 'activity.py', 'manual_runner.py', 'credentials.py', 'task_contract.py', 'wait_worker.py', 'native_task_cli.py', 'install_host_review.py'):
        shutil.copyfile(Path(__file__).with_name(name), destination / name)
    # A help-only service candidate: no coding task, board creation, credential, or timer.
    (destination / 'rras-engineering-check.service').write_text('''[Unit]
Description=RRAS engineering credential-free CLI check (review only)
[Service]
Type=oneshot
User=jarvis-codex-engineering
Group=jarvis-codex-engineering
UMask=0077
WorkingDirectory=/var/lib/rras-engineering
Environment=HOME=/var/lib/rras-engineering
Environment=HERMES_HOME=/var/lib/rras-engineering
Environment=CODEX_HOME=/var/lib/rras-engineering/codex
Environment=HERMES_KANBAN_WORKSPACES_ROOT=/var/lib/rras-engineering/workspaces
Environment=PATH=/opt/rras-engineering/current/runtime/bin:/opt/rras-engineering/current/runtime/codex-path:/usr/bin:/bin
ExecStart=/opt/rras-engineering/current/venv/bin/hermes kanban --help
NoNewPrivileges=yes
CapabilityBoundingSet=
AmbientCapabilities=
KillMode=control-group
TimeoutStartSec=30
MemoryMax=1G
TasksMax=128
CPUQuota=100%
# No Install section; no timer; not a task runner.
''')
    manifest = {'schema_version': 1, 'files': {
        str(p.relative_to(destination)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(destination.rglob('*')) if p.is_file()}}
    (destination / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--destination', type=Path, required=True)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--binary', type=Path, required=True)
    p.add_argument('--model', required=True)
    p.add_argument('--uv',type=Path)
    a = p.parse_args()
    prepare(a.destination, a.source, a.binary, a.model, a.uv)
    print(a.destination)
