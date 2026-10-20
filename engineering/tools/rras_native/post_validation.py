"""Inert contracts for independent validation; no filesystem or process execution.

Only trusted callers may supply captured admission and host observations. Passing
this schema never authenticates an input, launches a check or permits publication.
"""
import importlib.util
from pathlib import Path
import re

UNIT = 'rras-coding-task.service'


def local(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(value, length):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{' + str(length) + '}', value):
        raise ValueError('exact object digest required')
    return value


def plan(review, prepared, finish_sha256):
    """Bind the registered recipe to an independently reconstructed review tree.

    The eventual host must verify protected custody and actual Git objects first.
    The validation checkout must retain baseline HEAD with *unstaged* edits: the
    installed `git diff --check` recipe would be vacuous on a clean review commit.
    """
    admission = review['admission']
    compiled = local('repository_admission').compile_snapshot(
        admission['registration'], admission['work_item'], review['hermes_project'])
    request = compiled['request']
    if request != review['request']:
        raise ValueError('validation request differs from exact admitted recipe')
    if (prepared['repository_id'] != request['repository_id'] or
            prepared['task_id'] != request['task_id'] or
            prepared['branch'] != review['review_branch'] or
            prepared['baseline'] != review['baseline_commit'] or
            prepared['baseline'] != admission['work_item']['baseline']['commit']):
        raise ValueError('prepared review differs from admitted work')
    sha(prepared['baseline'], 40);sha(prepared['commit'], 40)
    sha(prepared['export_id'], 64);sha(finish_sha256, 64)
    a = local('activity')
    identity = {k: prepared[k] for k in ('repository_id', 'task_id', 'branch', 'baseline', 'commit', 'export_id')}
    result = dict(schema_version=1, identity=identity, finish_sha256=finish_sha256,
        registration_sha256=compiled['registration_sha256'], work_item_sha256=compiled['work_item_sha256'],
        validation_id=admission['work_item']['validation_id'], argv=request['validation_argv'],
        timeout_seconds=request['validation_timeout_seconds'], unit=UNIT, uid=996,
        checkout_mode='baseline_with_unstaged_review_tree', network=False, credentials=False,
        execution_authorized=False, publication_authorized=False)
    # Deep copy: caller mutation of argv/identity must not change a retained plan.
    return local('workflow_journal').decode(a.encoded(result))


def service_argv(contract, workspace):
    """Render only the fixed isolated service; caller must authenticate/rebuild plan.

    This is not a CLI. The future host must stage/verify the workspace, take the
    global slot, persist a one-use fence and bound private output before invocation.
    """
    if (contract['unit'] != UNIT or type(contract['uid']) is not int or contract['uid'] != 996 or
            contract['network'] is not False or contract['credentials'] is not False or
            contract['checkout_mode'] != 'baseline_with_unstaged_review_tree'):
        raise ValueError('fixed validator isolation required')
    argv = contract['argv']; seconds = contract['timeout_seconds']
    if (type(seconds) is not int or not 0 < seconds <= 60 or not isinstance(argv, list) or
            not 0 < len(argv) <= 64 or any(not isinstance(x, str) or not x or '\0' in x or len(x) > 4096 or '$' in x or '%' in x for x in argv) or
            not Path(argv[0]).is_absolute()):
        raise ValueError('bounded reviewed recipe required')
    path = Path(workspace)
    if (not isinstance(workspace, str) or not path.is_absolute() or str(path) != workspace or
            '..' in path.parts or not path.is_relative_to('/var/lib/rras-coding-tasks') or
            path == Path('/var/lib/rras-coding-tasks') or
            not re.fullmatch(r'/[A-Za-z0-9_./-]+', workspace)):
        raise ValueError('dedicated validation workspace required')
    properties = [
        'User=jarvis-codex-engineering', 'Group=jarvis-codex-engineering',
        'WorkingDirectory=' + workspace, 'UMask=0077', 'NoNewPrivileges=yes',
        'CapabilityBoundingSet=', 'KillMode=control-group', 'RuntimeMaxSec=' + str(seconds),
        'TimeoutStopSec=10', 'MemoryMax=1G', 'TasksMax=128', 'CPUQuota=100%',
        'PrivateNetwork=yes', 'RestrictAddressFamilies=AF_UNIX', 'PrivateTmp=yes',
        'ProtectSystem=strict', 'ProtectHome=yes', 'ReadWritePaths=' + workspace,
        'InaccessiblePaths=/etc/rras-engineering /run/credentials /var/lib/rras-workflow /opt/rras-coding-jobs',
    ]
    result = ['/usr/bin/systemd-run', '--unit', UNIT, '--service-type=exec', '--wait', '--pipe', '--collect']
    for prop in properties: result.extend(['-p', prop])
    return result + ['/usr/bin/env', '-i', '--', 'PATH=/usr/bin:/bin', 'LANG=C.UTF-8',
        'HOME=' + workspace, 'PYTHONDONTWRITEBYTECODE=1', 'GIT_CONFIG_NOSYSTEM=1',
        'GIT_CONFIG_GLOBAL=/dev/null', 'GIT_TERMINAL_PROMPT=0', *argv]


def observed_result(contract, observation):
    """Classify host facts, never worker JSON; missing stop/tree facts stay uncertain."""
    fields = {'plan_sha256', 'service_exit', 'host_stop_verified', 'tree_before', 'tree_after', 'expected_tree'}
    if set(observation) != fields:
        raise ValueError('exact host validation observations required')
    a = local('activity'); digest = a.digest(a.encoded(contract))
    if observation['plan_sha256'] != digest:
        raise ValueError('host result belongs to another plan')
    code = observation['service_exit']
    if code is not None and (type(code) is not int or not -255 <= code <= 255):
        raise ValueError('bounded host return code required')
    if type(observation['host_stop_verified']) is not bool:
        raise ValueError('explicit host stop observation required')
    for field in ('tree_before', 'tree_after', 'expected_tree'):
        if observation[field] is not None: sha(observation[field], 40)
    complete = (observation['host_stop_verified'] and code is not None and
        observation['expected_tree'] is not None and
        observation['tree_before'] == observation['expected_tree'] == observation['tree_after'])
    return dict(schema_version=1, plan_sha256=digest,
        outcome=('succeeded' if code == 0 else 'failed') if complete else 'uncertain',
        independently_executed_check=complete, task_success_established=False,
        human_acceptance=False, publication_authorized=False, retry_authorized=False)
