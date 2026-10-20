"""Durable observed control facts; never native-task success or retry authority."""
from pathlib import Path
import importlib.util
import hashlib


def local(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def stable(prefix, *parts):
    return prefix + hashlib.sha256(local('activity').encoded(list(parts))).hexdigest()[:32]


def journal(review):
    path = review['admission'].get('journal')
    if path is None:
        return None  # Compatibility with existing source-only review format.
    local('operator_control').trusted(path)
    return local('workflow_journal').Journal(path)


def record(review, review_id, phase, authorization_id=None, facts=None):
    store = journal(review)
    if store is None:
        return
    a = local('activity')
    binding = review['admission']
    actor = {'type': 'service', 'id': 'operator-control'}
    provenance = {'kind': 'observed', 'source': {'namespace': 'review', 'id': review_id},
                  'source_sha256': review_id, 'recorded_by': actor}
    work = binding['work_item']
    references = [{'namespace': 'review', 'id': review_id}]
    if authorization_id is not None:
        references.append({'namespace': 'authorization', 'id': authorization_id})
    definitions = {
        'captured': ('review.captured', 'pending', 'Protected review captured; execution remains unapproved.'),
        'approved': ('execution.approval_recorded', 'approved', 'Protected one-use execution authorization exists.'),
        'consumed': ('recovery.recorded', 'uncertain', 'Authorization consumed; service or model execution is not established.'),
        'staged': ('recovery.recorded', 'uncertain', 'Launch inputs staged; service acceptance is not established.'),
        'returned': ('recovery.recorded', 'uncertain', 'Service client returned; task success is not established.'),
    }
    kind, outcome, summary = definitions[phase]
    attempt = None
    attempt_id = None
    if phase in {'consumed', 'staged', 'returned'}:
        attempt_id = stable('att_', authorization_id)
        attempt = {'attempt_id': attempt_id, 'work_item_id': work['work_item_id'],
            'work_item_sha256': binding['work_item_sha256'], 'repository_id': work['repository_id'],
            'registration_sha256': binding['registration_sha256'], 'actor': actor, 'provenance': provenance,
            'mode': work['mode'], 'executor': 'native_worker', 'baseline': work['baseline'],
            'authorization_reference': {'namespace': 'authorization', 'id': authorization_id},
            'delegation_reference': None, 'references': references}
    artifacts = {}
    refs = []
    if facts is not None:
        # Only explicitly bounded mechanical facts, never service stdout or paths.
        if set(facts) != {'service_exit', 'host_stop_verified'} or type(facts['service_exit']) is not int or type(facts['host_stop_verified']) is not bool:
            raise ValueError('invalid service facts')
        raw = a.encoded(facts)
        sha = a.digest(raw)
        artifacts[sha] = raw
        refs = [{'artifact_id': stable('art_', authorization_id, phase), 'sha256': sha,
                 'media_type': 'application/json', 'visibility': 'operator_only', 'purpose': 'execution'}]
    event = {'event_id': stable('evt_', review_id, authorization_id, phase),
             'work_item_id': work['work_item_id'], 'work_item_sha256': binding['work_item_sha256'],
             'attempt_id': attempt_id, 'actor': actor, 'provenance': provenance,
             'event_type': kind, 'outcome': outcome, 'summary': summary,
             'artifacts': refs, 'references': references, 'corrects_event_id': None, 'decision_subject': None}
    return store.append([binding['registration'], work], artifacts, transition=(event, attempt))


def before_launch(review, review_id, authorization_id, approval):
    if journal(review) is None:
        return
    if (approval['authorization_id'] != authorization_id or approval['review_id'] != review_id or
            approval['execution_authorized'] is not True or approval['publication_authorized'] is not False or
            approval['authorized_os_uid'] != 0):
        raise ValueError('invalid authorization evidence')
    record(review, review_id, 'captured')
    record(review, review_id, 'approved', authorization_id)
