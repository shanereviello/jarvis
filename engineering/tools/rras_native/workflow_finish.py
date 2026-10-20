"""Protected stopped-worker result custody and provenance-aware journal recording.

No service mutation, model, Git/network publication or task lifecycle write.
Worker results remain imported claims; protected host stop is a separate fact.
"""
import importlib.util
import os
from pathlib import Path
import re
import stat


def local(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def decode(raw):
    return local('workflow_journal').decode(raw)


def inputs(state, authorization_id):
    operator = local('operator_control')
    state = operator.require_operator(state)
    authorization_id = operator.authorization(authorization_id)
    read = local('publication_custody').root_bytes
    auth = decode(read(state / (authorization_id + '.approval.json'), 1024 * 1024))
    review = local('approval').read_review(state, auth['review_id'])
    if (auth['authorization_id'] != authorization_id or auth['authorized_os_uid'] != 0 or
            auth['execution_authorized'] is not True or auth['publication_authorized'] is not False or
            'journal' not in review.get('admission', {})):
        raise ValueError('configured managed approval required')
    consumed = decode(read(state / (authorization_id + '.consumed.json'), 1024 * 1024))
    link = decode(read(state / (authorization_id + '.launch.json'), 1024 * 1024))
    result = decode(read(state / (authorization_id + '.result.json'), 1024 * 1024))
    for row in (consumed, link, result):
        if row['authorization_id'] != authorization_id or row['review_id'] != auth['review_id']:
            raise ValueError('launch association mismatch')
    if (type(result.get('service_exit')) is not int or result.get('host_stop_verified') is not True or
            result != dict(link, service_exit=result['service_exit'], host_stop_verified=True) or
            link['submission_id'] != review['submission_id'] or link.get('review_branch') != review.get('review_branch') or
            link['publication_authorized'] is not False or link['unit'] != local('approved_launch').UNIT or
            not re.fullmatch('[0-9a-f]{32}', link['run_id'])):
        raise ValueError('verified stopped launch result required')
    work = Path(link['work'])
    if not work.is_absolute() or str(work) != str(work.resolve(strict=True)):
        raise ValueError('exact launch work path required')
    return review, auth, consumed, link, result


def classify(review, host, evidence, context=None):
    """Classify a captured RUNNER REPORT, never independently authenticate a worker."""
    if (evidence.get('scope') != 'native-manual-admitted-task' or
            type(evidence.get('success')) is not bool or evidence.get('lifecycle_mutated_by_runner') is not False):
        raise ValueError('recognized native runner result required')
    wait = evidence.get('wait')
    if wait is None:
        if evidence['success'] or context is not None:
            raise ValueError('incomplete result claims success or contradicts native context')
        return {'outcome': 'uncertain', 'terminal': False, 'validation': None}
    if (not isinstance(wait, dict) or type(wait.get('success')) is not bool or
            type(wait.get('worker_stop_verified')) is not bool):
        raise ValueError('invalid native wait report')
    task, run = evidence.get('native_task'), evidence.get('native_run')
    if (not isinstance(task, str) or not re.fullmatch('t_[A-Za-z0-9]+', task) or
            type(run) is not int or run < 1 or context is None or
            context.get('task') != task or type(context.get('run_id')) is not int or context.get('run_id') != run or
            type(context.get('schema_version')) is not int or context.get('schema_version') != 1):
        raise ValueError('native task/run context mismatch')
    root = Path(host['work'])
    if (context.get('python') != local('native_task_cli').TRUSTED_PYTHON or
            context.get('home') != str(root / 'home/profiles/rras-engineering') or
            context.get('board') != str(root / 'home/kanban/kanban.db')):
        raise ValueError('native context path mismatch')
    workspace = evidence.get('workspace')
    base = root.parent / 'repo/.worktrees'
    if not isinstance(workspace, str) or str(Path(workspace)) != workspace or Path(workspace).parent != base or Path(workspace).name in ('', '.', '..'):
        raise ValueError('native workspace outside assigned checkout')
    validation = None
    if 'validation_exit' in evidence:
        if (type(evidence['validation_exit']) is not int or evidence.get('validation_stop_verified') is not True or
                evidence.get('mechanical_validation') != ('passed' if evidence['validation_exit'] == 0 else 'failed')):
            raise ValueError('inconsistent validation report')
        validation = 'succeeded' if evidence['validation_exit'] == 0 else 'failed'
    if not wait['worker_stop_verified']:
        if evidence['success'] or validation is not None:
            raise ValueError('unstopped worker cannot claim validated success')
        return {'outcome': 'uncertain', 'terminal': False, 'validation': None}
    if (type(wait.get('exit_code')) is not int or not isinstance(wait.get('native_status'), str) or
            wait.get('outcome') not in ('completed', 'failed')):
        raise ValueError('terminal native wait facts required')
    if wait['native_status'] not in {'done', 'failed', 'cancelled'}:
        if evidence['success']: raise ValueError('nonterminal native status cannot claim success')
        return {'outcome': 'uncertain', 'terminal': False, 'validation': validation}
    native_success = wait['exit_code'] == 0 and wait['native_status'] == 'done'
    if wait['success'] != native_success or wait['outcome'] != ('completed' if native_success else 'failed'):
        raise ValueError('contradictory native completion report')
    success = native_success and validation == 'succeeded' and evidence.get('phase') == 'finished'
    if evidence['success'] != success or (success and host['service_exit'] != 0) or (not success and host['service_exit'] == 0):
        raise ValueError('host/native/validation outcome mismatch')
    return {'outcome': 'succeeded' if success else 'failed', 'terminal': True, 'validation': validation}


def capture(state, authorization_id, destination):
    review, auth, consumed, link, host = inputs(state, authorization_id)
    destination = Path(destination)
    if not destination.is_absolute(): raise ValueError('absolute custody destination required')
    local('approved_launch').trusted(destination.parent)
    if destination.exists() or destination.is_symlink():
        raise ValueError('fresh finish custody destination required')
    slot = local('approved_launch').slot
    slot()
    read = local('publication_capture').worker_bytes
    root = Path(host['work'])
    raw = read(root / 'evidence.json', 1024 * 1024)
    evidence = decode(raw)
    # The reviewed request is also checked against the root-staged job copy.
    job_request = decode(local('publication_custody').root_bytes(Path(host['job']) / 'request.json', 1024 * 1024))
    if job_request != review['request']:
        raise ValueError('staged request changed')
    members = {'evidence.json': raw}
    context = None
    if 'wait' in evidence:
        members['native-context.json'] = read(root / 'native-task-context.json', 8192)
        context = decode(members['native-context.json'])
    facts = classify(review, host, evidence, context)
    # Export is required before recording a successful terminal report. Failed and
    # interrupted reports can be retained without an export and cannot publish.
    a = local('activity')
    if facts['outcome'] == 'succeeded' and not evidence.get('export'):
        raise ValueError('successful result requires an export')
    if 'export' in evidence:
        export_id = evidence['export']['export_id']
        if not re.fullmatch('[0-9a-f]{64}', export_id): raise ValueError('exact export ID required')
        directory = root / 'index' / review['request']['task_id'] / 'exports' / export_id
        if evidence['export'].get('path') != str(directory): raise ValueError('export location mismatch')
        manifest_raw = read(directory / 'manifest.json', 1024 * 1024)
        manifest = decode(manifest_raw)
        if a.digest(a.encoded(manifest)) != export_id: raise ValueError('export identity mismatch')
        if (manifest['task']['task_id'] != review['request']['task_id'] or
                manifest['task']['repository_id'] != review['request']['repository_id'] or
                manifest['task']['baseline_commit'] != review['baseline_commit'] or
                manifest['head_commit'] != review['baseline_commit'] or
                manifest['worktree'] != evidence['workspace'] or
                manifest['binding']['hermes_task'] != evidence['native_task'] or
                str(manifest['binding']['hermes_run']) != str(evidence['native_run'])):
            raise ValueError('export task/run/baseline mismatch')
        if not 1 <= len(manifest['files']) <= 10: raise ValueError('bounded export required')
        members['manifest.json'] = manifest_raw
        for name, entry in manifest['files'].items():
            if not re.fullmatch(r'(changes\.patch|status\.porcelain|index\.patch|reported-log-[0-9]\.txt|additional-artifact-[01]\.json)', name):
                raise ValueError('unexpected export member')
            data = read(directory / name, 4 * 1024 * 1024)
            if len(data) != entry['size_bytes'] or a.digest(data) != entry['sha256']:
                raise ValueError('export member changed')
            members['artifacts/' + name] = data
        if decode(members['artifacts/additional-artifact-1.json']) != review['request']:
            raise ValueError('export request mismatch')
    if sum(map(len, members.values())) > 16 * 1024 * 1024: raise ValueError('oversized custody')
    slot()
    destination.mkdir(mode=0o700)
    a.fsync_directory(destination.parent)
    members.update({'review.json': a.encoded(review), 'approval.json': a.encoded(auth),
                    'consumed.json': a.encoded(consumed), 'host-result.json': a.encoded(host)})
    if sum(map(len, members.values())) > 16 * 1024 * 1024: raise ValueError('oversized complete custody')
    for name, data in members.items():
        (destination / name).parent.mkdir(mode=0o700, exist_ok=True)
        a.absent(destination / name, data)
    receipt = {'schema_version': 1, 'authorization_id': authorization_id,
               'review_id': auth['review_id'], 'facts': facts,
               'files': {name: a.digest(data) for name, data in members.items()}}
    a.absent(destination / 'finish-capture.json', a.encoded(receipt))
    return {'captured': True, 'outcome': facts['outcome'], 'terminal_claim': facts['terminal'],
            'publication_authorized': False, 'execution_retried': False}


def load(custody):
    if os.getuid() != 0 or os.geteuid() != 0: raise ValueError('root finish recording required')
    local('approved_launch').trusted(Path(__file__))
    read = local('publication_custody').root_bytes
    if not Path(custody).is_absolute(): raise ValueError('absolute custody directory required')
    root = local('approved_launch').trusted(Path(custody))
    if not root.is_dir() or stat.S_IMODE(root.stat().st_mode) != 0o700:
        raise ValueError('private finish custody directory required')
    receipt = decode(read(root / 'finish-capture.json', 1024 * 1024))
    if receipt.get('schema_version') != 1 or not 4 <= len(receipt['files']) <= 20:
        raise ValueError('invalid finish receipt')
    members = {}
    for name, sha in receipt['files'].items():
        p = Path(name)
        if p.is_absolute() or '..' in p.parts or str(p) != name or len(p.parts) > 2:
            raise ValueError('invalid custody member')
        raw = read(root / p, 4 * 1024 * 1024)
        if local('activity').digest(raw) != sha: raise ValueError('finish custody changed')
        members[name] = raw
    review, host = decode(members['review.json']), decode(members['host-result.json'])
    evidence = decode(members['evidence.json'])
    if (local('activity').digest(local('activity').encoded(review)) != receipt['review_id'] or
            host['review_id'] != receipt['review_id'] or host['authorization_id'] != receipt['authorization_id'] or
            host.get('host_stop_verified') is not True or type(host.get('service_exit')) is not int):
        raise ValueError('finish review/host identity mismatch')
    for name in ('approval.json','consumed.json'):
        row=decode(members[name])
        if row['authorization_id']!=receipt['authorization_id'] or row['review_id']!=receipt['review_id']:
            raise ValueError('captured control association mismatch')
    facts = classify(review, host, evidence, decode(members['native-context.json']) if 'native-context.json' in members else None)
    if facts != receipt['facts']: raise ValueError('finish outcome changed')
    return receipt, review, members


def record(custody):
    receipt, review, members = load(custody)
    events = local('managed_events'); store = events.journal(review)
    if store is None: raise ValueError('configured managed journal required')
    auth = receipt['authorization_id']; review_id = receipt['review_id']; facts = receipt['facts']
    # Repair only protected control facts first; this never launches a service.
    approval = decode(members['approval.json'])
    events.before_launch(review, review_id, auth, approval)
    events.record(review, review_id, 'consumed', auth)
    a = local('activity'); capture_id = a.digest(a.encoded(receipt))
    actor = {'type': 'service', 'id': 'workflow-finish'}
    provenance = {'kind': 'imported', 'source': {'namespace': 'external', 'id': 'finish-capture:' + capture_id},
                  'source_sha256': capture_id, 'recorded_by': actor}
    work = review['admission']['work_item']
    phases = [('artifact.recorded', 'succeeded', 'Protected stopped-worker report captured; execution claims retain imported provenance.')]
    if facts['validation'] is not None:
        phases.append(('validation.finished', facts['validation'], 'Captured runner reports mechanical validation; human acceptance remains separate.'))
    phases.append(('attempt.finished' if facts['terminal'] else 'recovery.recorded', facts['outcome'],
                   'Captured native runner result; publication, merge and release are not established.'))
    for kind, outcome, summary in phases:
        event = {'event_id': events.stable('evt_', auth, 'finish', kind),
                 'work_item_id': work['work_item_id'], 'work_item_sha256': review['admission']['work_item_sha256'],
                 'attempt_id': events.stable('att_', auth), 'actor': actor, 'provenance': provenance,
                 'event_type': kind, 'outcome': outcome, 'summary': summary,
                 'artifacts': [{'artifact_id': events.stable('art_', auth, 'finish-capture'), 'sha256': capture_id,
                     'media_type': 'application/json', 'visibility': 'operator_only', 'purpose': 'execution'}],
                 'references': [{'namespace': 'authorization', 'id': auth}, {'namespace': 'review', 'id': review_id}],
                 'corrects_event_id': None, 'decision_subject': None}
        store.append([], {capture_id: a.encoded(receipt)}, transition=(event, None))
    return {'recorded': True, 'outcome': facts['outcome'], 'terminal_claim': facts['terminal'],
            'provenance': 'imported', 'publication_authorized': False, 'execution_retried': False}
