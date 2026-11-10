"""One bounded future-session collection pass; integrations supplied by caller.

The caller supplies authenticated registry, isolated worker and scoped history
delivery functions. No default network endpoint, Docker privilege or service
activation is created by this module.
"""
import importlib.util
import os
from pathlib import Path
import uuid


def local(name):
    spec = importlib.util.spec_from_file_location('future_coordinator_' + name, Path(__file__).with_name(name + '.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def run_once(*, organization_id, cutoff, cursor, query, worker, flush):
    selection = local('hermes_capture_selection')
    selection.identifier(organization_id)
    selection.timestamp(cutoff)
    if (type(cursor) is not dict or set(cursor) != {'after_time', 'after_id'}):
        raise ValueError('exact future cursor required')
    selection.timestamp(cursor['after_time'])
    selection.identifier(cursor['after_id'])
    page = query(dict(cursor))
    rows = selection.select_page(page, organization_id=organization_id, cutoff=cutoff, **cursor)
    result = worker(dict(page=page, **cursor))
    if (type(result) is not dict or set(result) != {'contract', 'sessions', 'models_started'} or
            result['contract'] != 'hermes-future-capture-page.v1' or result['models_started'] != 0 or
            type(result['sessions']) is not list or len(result['sessions']) != len(rows)):
        raise ValueError('exact offline worker result required')
    for row, output in zip(rows, result['sessions']):
        if (type(output) is not dict or set(output) != {'session_id', 'changed'} or
                output['session_id'] != row['agent_session_id'] or type(output['changed']) is not bool):
            raise ValueError('worker session result differs')
    delivery = flush()
    if (type(delivery) is not dict or type(delivery.get('failed')) is not int or
            type(delivery.get('pending')) is not int or delivery['failed'] != 0 or delivery['pending'] != 0):
        raise ValueError('history delivery incomplete; retain cursor for replay')
    # A completed cycle restarts at the fixed cutoff to notice later changes in
    # earlier sessions. The durable capture spool deduplicates unchanged source.
    next_cursor = (dict(after_time=rows[-1]['created_at'], after_id=rows[-1]['agent_session_id'])
                   if len(rows) == 4 else dict(after_time=cutoff, after_id=str(uuid.UUID(int=0))))
    return dict(cursor=next_cursor, sessions=len(rows), delivery=delivery, models_started=0)


def save_cursor(directory, cursor):
    intake = local('capture_intake')
    directory = intake.private(directory, True)
    target = directory / 'hermes-future-cursor.json'
    pending = directory / 'hermes-future-cursor.pending'
    raw = intake.local('contract').encoded(cursor)
    if target.exists() or target.is_symlink():
        intake.private(target)
    if pending.exists() or pending.is_symlink():
        intake.private(pending)
        # A prior pass may have finished collection before its cursor rename.
        # Never discard conflicting durable state to move a cursor forward.
        if pending.read_bytes() != raw:
            raise ValueError('interrupted future cursor requires inspection')
    else:
        fd = os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    os.replace(pending, target)
    intake.sync(directory)
