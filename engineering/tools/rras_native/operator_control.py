"""Operator interface for admitted work; no scheduler or automatic approvals.

Prepare is unprivileged. Capture/review/approve/launch/evidence require a protected
installation and root operator. Launch alone can spend, after explicit one-use
approval. Source tests must use a fake service manager and harmless credentials.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import sqlite3


def local(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def trusted(path):
    path = Path(path)
    if not path.is_absolute():
        raise ValueError('absolute protected path required')
    return local('approved_launch').trusted(path)


def require_operator(state):
    if os.getuid() != 0 or os.geteuid() != 0:
        raise ValueError('root operator required')
    trusted(Path(__file__))
    state = trusted(state)
    if not state.is_dir() or state.stat().st_mode & 0o777 != 0o700:
        raise ValueError('root-private 0700 control directory required')
    return state


def configuration(path):
    """A root-selected/root-protected configuration is the live admission source."""
    a = local('activity')
    path = trusted(path)
    if not path.is_absolute() or not path.is_file():
        raise ValueError('absolute protected configuration file required')
    # Single read: digest and parsed value describe the same bytes.
    raw = path.read_bytes()
    if len(raw) > 256 * 1024:
        raise ValueError('oversized configuration')
    def unique(pairs):
        row = {}
        for key, value in pairs:
            if key in row:
                raise ValueError('duplicate configuration key')
            row[key] = value
        return row
    value = json.loads(raw, object_pairs_hook=unique,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError('invalid number')))
    fields = {'schema_version', 'registration', 'hermes_project', 'profile', 'codex_config'}
    if not isinstance(value, dict) or set(value) not in (fields, fields | {'journal'}) or type(value['schema_version']) is not int or value['schema_version'] != 1:
        raise ValueError('invalid operator configuration')
    local('workflow_records').validate_record(value['registration'])
    if value['registration']['kind'] != 'repository_registration':
        raise ValueError('repository registration required')
    a.identifier(value['hermes_project'])
    for field in ('profile', 'codex_config'):
        target = trusted(value[field])
        if not target.is_absolute() or not target.is_file():
            raise ValueError('absolute protected session file required')
    if 'journal' in value:
        local('workflow_journal').Journal(trusted(value['journal']))
    return value, a.digest(raw)


def control_files():
    """Fixed dependency set; never trust file names supplied in a proposal."""
    root = Path(__file__).parent
    names = ('operator_control.py', 'repository_admission.py', 'workflow_records.py',
             'approval.py', 'approved_launch.py', 'activity.py', 'task_contract.py',
             'managed_events.py', 'workflow_journal.py')
    return [root / name for name in names] + [local('workflow_records').SCHEMA]


def control_hashes():
    a = local('activity')
    return {str(path): a.digest(trusted(path).read_bytes()) for path in control_files()}


def candidate(proposals, candidate_id, config):
    a = local('activity')
    local('approval').exact_digest(candidate_id)
    snapshot = a.load(Path(proposals) / (candidate_id + '.admission.json'))
    if a.digest(a.encoded(snapshot)) != candidate_id:
        raise ValueError('candidate digest mismatch')
    # Candidate registry/policy/actor fields have no authority. Reconstruct against
    # the live protected registration and project, not the candidate's claim.
    expected = local('repository_admission').compile_snapshot(
        config['registration'], snapshot['work_item'], config['hermes_project'])
    if a.encoded(expected) != a.encoded(snapshot):
        raise ValueError('candidate does not match live admission')
    return expected


def capture(config_path, proposals, candidate_id, state, review_branch):
    state = require_operator(state)
    config, config_sha = configuration(config_path)
    snapshot = candidate(proposals, candidate_id, config)
    local('repository_admission').inspect_repository(snapshot)
    prefix = config['registration']['publication']['review_branch_prefix']
    if not isinstance(review_branch, str) or not review_branch.startswith(prefix):
        raise ValueError('review branch outside registered prefix')
    binding = {'schema_version': 1, 'configuration': str(Path(config_path)),
               'configuration_sha256': config_sha,
               'registration_sha256': snapshot['registration_sha256'],
               'work_item_sha256': snapshot['work_item_sha256'],
               'work_item': snapshot['work_item'], 'candidate_id': candidate_id,
               'proposal_source': 'operator_admission_candidate',
               'control_files': control_hashes()}
    if 'journal' in config:
        binding.update(journal=config['journal'], registration=config['registration'])
    baseline = snapshot['work_item']['baseline']
    result = local('approval').snapshot(snapshot['request'], config['registration']['source']['canonical_path'],
        config['hermes_project'], state, config['profile'], config['codex_config'], candidate_id,
        config_sha, baseline_ref=baseline['ref'], expected_baseline=baseline['commit'],
        review_branch=review_branch, admission=binding)
    local('managed_events').record(result['review'], result['review_id'], 'captured')
    return result


def validate_review(review, config_path):
    """Repeat live admission/baseline checks before approval or consumption.

    The reviewed work stays immutable even if its untrusted proposal is edited.
    Editing/removing/replacing protected configuration invalidates the review.
    """
    a = local('activity')
    binding = review['admission']
    fields = {'schema_version', 'configuration', 'configuration_sha256', 'registration_sha256',
              'work_item_sha256', 'work_item', 'candidate_id', 'proposal_source', 'control_files'}
    if 'journal' in binding:
        fields |= {'journal', 'registration'}
    if set(binding) != fields or type(binding['schema_version']) is not int or binding['schema_version'] != 1:
        raise ValueError('invalid admission binding')
    if str(config_path) != binding['configuration']:
        raise ValueError('different live configuration path')
    config, config_sha = configuration(config_path)
    if config.get('journal') != binding.get('journal') or ('journal' in binding and binding['registration'] != config['registration']):
        raise ValueError('journal binding changed')
    if config_sha != binding['configuration_sha256'] or config_sha != review['policy_sha256']:
        raise ValueError('live admission changed')
    if binding['control_files'] != control_hashes():
        raise ValueError('reviewed control code changed')
    snapshot = local('repository_admission').compile_snapshot(
        config['registration'], binding['work_item'], config['hermes_project'])
    expected = {'registration_sha256': snapshot['registration_sha256'],
                'work_item_sha256': snapshot['work_item_sha256'],
                'candidate_id': a.digest(a.encoded(snapshot)),
                'proposal_source': 'operator_admission_candidate'}
    if any(binding[key] != value for key, value in expected.items()):
        raise ValueError('admission association changed')
    baseline = snapshot['work_item']['baseline']
    if (review['submission_id'] != binding['candidate_id'] or review['request'] != snapshot['request'] or
            review['canonical_repository'] != config['registration']['source']['canonical_path'] or
            review['hermes_project'] != config['hermes_project'] or
            review['baseline_commit'] != baseline['commit'] or review['baseline_ref'] != baseline['ref'] or
            not review.get('review_branch', '').startswith(config['registration']['publication']['review_branch_prefix']) or
            review['execution_authorized'] is not False or review['publication_authorized'] is not False):
        raise ValueError('review differs from admitted work')
    if not re.fullmatch(r'codex/[A-Za-z0-9][A-Za-z0-9_-]{0,120}', review['review_branch']):
        raise ValueError('dedicated review branch required')
    for field in ('profile', 'codex_config'):
        if review[field] != str(Path(config[field]).resolve(strict=True)) or a.digest(trusted(review[field]).read_bytes()) != review[field + '_sha256']:
            raise ValueError('session configuration changed')
    for name, digest in review['runner_files'].items():
        if a.digest(trusted(Path(__file__).with_name(name)).read_bytes()) != digest:
            raise ValueError('reviewed runner changed')
    local('repository_admission').inspect_repository(snapshot)
    return snapshot


def review(state, review_id, config_path):
    state = require_operator(state)
    record = local('approval').read_review(state, review_id)
    validate_review(record, config_path)
    # Private operator view: bounded request, never profile/config content or logs.
    return {'review_id': review_id, 'request': record['request'],
            'baseline': {'ref': record['baseline_ref'], 'commit': record['baseline_commit']},
            'review_branch': record['review_branch'],
            'registration_sha256': record['admission']['registration_sha256'],
            'work_item_sha256': record['admission']['work_item_sha256'],
            'execution_authorized': False, 'publication_authorized': False}


def approve(state, review_id, config_path, *, approve_one_execution=False):
    if approve_one_execution is not True:
        raise ValueError('explicit one-execution approval required')
    state = require_operator(state)
    record = local('approval').read_review(state, review_id)
    validate_review(record, config_path)
    result = local('approval').approve(state, review_id)
    local('managed_events').record(record, review_id, 'approved', result['authorization_id'])
    return result


def launch(state, authorization_id, config_path, jobs, workers, credential):
    state = require_operator(state)
    if any(not Path(path).is_absolute() for path in (jobs, workers, credential)):
        raise ValueError('absolute launch paths required')
    auth = local('activity').load(state / (authorization(authorization_id) + '.approval.json'))
    record = local('approval').read_review(state, auth['review_id'])
    validate_review(record, config_path)
    # approved_launch checks admission again before consume, retains global slot
    # exclusion and performs the only service/model-capable action in this module.
    result = local('approved_launch').launch(state, authorization_id, jobs, workers, config_path, credential)
    return result


def authorization(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{32}', value):
        raise ValueError('exact authorization ID required')
    return value


def evidence(state, authorization_id):
    """Bounded operator summary of protected launch records, not task success."""
    state = require_operator(state)
    a, approval = local('activity'), local('approval')
    authorization_id = authorization(authorization_id)
    auth = a.load(state / (authorization_id + '.approval.json'))
    record = approval.read_review(state, auth['review_id'])
    if (auth['authorization_id'] != authorization_id or auth['execution_authorized'] is not True or
            auth['publication_authorized'] is not False or auth['authorized_os_uid'] != 0):
        raise ValueError('invalid authorization record')
    answer = {'authorization_id': authorization_id, 'review_id': auth['review_id'],
              'repository_id': record['request']['repository_id'],
              'task_id': record['request']['task_id'], 'state': 'approved_not_consumed',
              'publication_authorized': False, 'task_success_established': False}
    if 'admission' in record:
        answer['work_item_sha256'] = record['admission']['work_item_sha256']
        answer['work_item_id'] = record['admission']['work_item']['work_item_id']
        answer['work_item_revision'] = record['admission']['work_item']['revision']
    for suffix, phase in (('consumed', 'consumed_outcome_unknown'),
                          ('launch', 'launch_recorded'), ('result', 'service_returned')):
        path = state / (authorization_id + '.' + suffix + '.json')
        if path.exists() or path.is_symlink():
            if suffix != 'consumed' and answer['state'] == 'approved_not_consumed':
                raise ValueError('missing consumption evidence')
            if suffix == 'result' and answer['state'] != 'launch_recorded':
                raise ValueError('missing launch evidence')
            row = a.load(path)
            if row['authorization_id'] != authorization_id or row['review_id'] != auth['review_id']:
                raise ValueError('evidence association mismatch')
            answer['state'] = phase
            if suffix == 'result':
                if type(row['service_exit']) is not int or type(row['host_stop_verified']) is not bool:
                    raise ValueError('invalid service result')
                answer.update(service_exit=row['service_exit'], host_stop_verified=row['host_stop_verified'])
    return answer


def reconcile(state, authorization_id):
    """Rebuild missing journal facts from protected receipts; never retry/stop work."""
    state = require_operator(state)
    view = evidence(state, authorization_id)
    a = local('activity')
    record = local('approval').read_review(state, view['review_id'])
    events = local('managed_events')
    if events.journal(record) is None:
        raise ValueError('review has no configured journal')
    events.record(record, view['review_id'], 'captured')
    events.record(record, view['review_id'], 'approved', authorization_id)
    for suffix, phase in (('consumed', 'consumed'), ('launch', 'staged'), ('result', 'returned')):
        path = state / (authorization_id + '.' + suffix + '.json')
        if path.exists():
            receipt = a.load(path)
            facts = {key: receipt[key] for key in ('service_exit', 'host_stop_verified')} if suffix == 'result' else None
            events.record(record, view['review_id'], phase, authorization_id, facts)
    return dict(view, journal_reconciled=True, execution_retried=False)


def finish_capture(state, authorization_id, destination):
    """Preserve stopped-worker reports; never approve publication or retry work."""
    return local('workflow_finish').capture(state, authorization_id, destination)


def finish_record(custody):
    """Replay immutable protected finish custody into the configured journal."""
    return local('workflow_finish').record(custody)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    prepare = sub.add_parser('prepare')
    for name in ('registration', 'work-item', 'hermes-project', 'state'):
        prepare.add_argument('--' + name, required=True)
    capture_parser = sub.add_parser('capture')
    for name in ('config', 'proposals', 'candidate-id', 'state', 'review-branch'):
        capture_parser.add_argument('--' + name, required=True)
    for command in ('review', 'approve'):
        parser = sub.add_parser(command)
        for name in ('state', 'review-id', 'config'):
            parser.add_argument('--' + name, required=True)
        if command == 'approve':
            parser.add_argument('--approve-one-execution', action='store_true')
    launch_parser = sub.add_parser('launch')
    for name in ('state', 'authorization-id', 'config', 'jobs', 'workers', 'credential'):
        launch_parser.add_argument('--' + name, required=True)
    for command in ('evidence', 'reconcile'):
        evidence_parser = sub.add_parser(command)
        for name in ('state', 'authorization-id'):
            evidence_parser.add_argument('--' + name, required=True)
    finish = sub.add_parser('finish-capture')
    for name in ('state', 'authorization-id', 'destination'):
        finish.add_argument('--' + name, required=True)
    finish = sub.add_parser('finish-record')
    finish.add_argument('--custody', required=True)
    publication = sub.add_parser('publication-prepare')
    for name in ('finish-custody','policy','destination','package','operator'):
        publication.add_argument('--' + name, required=True)
    publication = sub.add_parser('publication-capture')
    for name in ('finish-custody','package','workspace','destination'):
        publication.add_argument('--' + name, required=True)
    publication.add_argument('--pr-receipt')
    publication = sub.add_parser('publication-record')
    for name in ('finish-custody','custody'):
        publication.add_argument('--' + name, required=True)
    args = p.parse_args(argv)
    try:
        if args.command == 'prepare':
            result = local('repository_admission').prepare(args.registration, args.work_item, args.hermes_project, args.state)
        elif args.command == 'capture':
            captured = capture(args.config, args.proposals, args.candidate_id, args.state, args.review_branch)
            result = {'review_id': captured['review_id'], 'execution_authorized': False, 'publication_authorized': False}
        elif args.command == 'review':
            result = review(args.state, args.review_id, args.config)
        elif args.command == 'approve':
            result = approve(args.state, args.review_id, args.config, approve_one_execution=args.approve_one_execution)
        elif args.command == 'launch':
            result = launch(args.state, args.authorization_id, args.config, args.jobs, args.workers, args.credential)
        elif args.command == 'publication-prepare':
            result = local('workflow_publication').prepare(args.finish_custody,args.policy,args.destination,args.package,args.operator)
        elif args.command == 'publication-capture':
            result = local('workflow_publication').capture(args.finish_custody,args.package,args.workspace,args.destination,args.pr_receipt)
        elif args.command == 'publication-record':
            result = local('workflow_publication').record(args.finish_custody,args.custody)
        elif args.command == 'finish-capture':
            result = finish_capture(args.state, args.authorization_id, args.destination)
        elif args.command == 'finish-record':
            result = finish_record(args.custody)
        elif args.command == 'reconcile':
            result = reconcile(args.state, args.authorization_id)
        else:
            result = evidence(args.state, args.authorization_id)
    except (ValueError, OSError, KeyError, TypeError, sqlite3.Error):
        p.exit(1, 'Operator command refused; preserve records and inspect admission/configuration.\n')
    print(json.dumps(result))
    if args.command == 'launch' and (result['service_exit'] != 0 or result['host_stop_verified'] is not True):
        p.exit(1)


if __name__ == '__main__':
    main()
