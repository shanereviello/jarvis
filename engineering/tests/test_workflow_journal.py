"""Durability, replay and projection tests with disposable local stores only."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from unittest.mock import patch

import pytest

import test_workflow_records as fixtures

MODULE = Path(__file__).resolve().parents[1] / 'tools/rras_native/workflow_journal.py'
spec = importlib.util.spec_from_file_location('workflow_journal', MODULE)
j = importlib.util.module_from_spec(spec)
spec.loader.exec_module(j)


@pytest.fixture
def store(tmp_path):
    root = tmp_path / 'private'
    root.mkdir(mode=0o700)
    return j.Journal(root, create=True)


def event_after(rows, **changes):
    row = fixtures.next_event(rows)
    row.update(changes)
    return row


def artifact_event(rows):
    raw = b'private fixture log; never publish raw bytes'
    sha = j.digest(raw)
    event = event_after(rows, event_type='artifact.recorded', artifacts=[{
        'artifact_id': 'art_' + '1' * 32, 'sha256': sha, 'media_type': 'text/plain',
        'visibility': 'operator_only', 'purpose': 'validation'}])
    return event, sha, raw


def run_cli(*args):
    return subprocess.run([sys.executable, str(MODULE), *map(str, args)], capture_output=True, text=True)


def test_committed_records_and_outbox_survive_reopen_with_no_delivery(store):
    rows = fixtures.history()
    assert store.append(rows)['inserted'] == 4
    reopened = j.Journal(store.root)
    assert len(reopened.records()) == 4
    pending = reopened.outbox()
    assert len(pending['pending']) == 4
    assert pending['delivery'] == 'not_implemented'
    assert reopened.append(rows)['already_present'] == 4
    assert reopened.outbox() == pending
    assert store.path.stat().st_mode & 0o777 == 0o600


def test_artifacts_records_and_queue_rollback_together(store):
    rows = fixtures.history()
    event, sha, raw = artifact_event(rows)
    with patch.object(j, '_commit', side_effect=RuntimeError('fixture precommit failure')):
        with pytest.raises(RuntimeError): store.append(rows + [event], {sha: raw})
    assert store.records() == []
    assert store.outbox()['pending'] == []
    with pytest.raises(ValueError): store.artifact(sha)
    store.append(rows + [event], {sha: raw})
    assert j.Journal(store.root).artifact(sha) == raw
    assert len(store.outbox()['pending']) == 5


def test_process_exit_before_commit_rolls_back_hot_journal(store, tmp_path):
    rows = fixtures.history()
    event, sha, raw = artifact_event(rows)
    source = tmp_path / 'input.json'
    source.write_text(json.dumps(rows + [event]))
    script = '''import importlib.util,os,sys
s=importlib.util.spec_from_file_location('journal',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
x=m.Journal(sys.argv[2]);m._commit=lambda db:os._exit(73)
x.append(m.load_json(sys.argv[3]),{sys.argv[4]:sys.argv[5].encode()})
'''
    result = subprocess.run([sys.executable, '-c', script, str(MODULE), str(store.root), str(source), sha, raw.decode()], capture_output=True)
    assert result.returncode == 73
    recovered = j.Journal(store.root)
    assert recovered.records() == []
    assert recovered.outbox()['pending'] == []
    with pytest.raises(ValueError): recovered.artifact(sha)
    assert recovered.append(rows)['inserted'] == 4


def test_process_commit_is_visible_after_restart(store, tmp_path):
    source = tmp_path / 'input.json'
    source.write_text(json.dumps(fixtures.history()))
    result = run_cli('append', '--store', store.root, '--records', source)
    assert result.returncode == 0, result.stderr
    assert len(j.Journal(store.root).outbox()['pending']) == 4


def test_concurrent_competing_event_sequences_preserve_one_complete_stream(store, tmp_path):
    rows = fixtures.history()
    store.append(rows)
    files = []
    for index in (1, 2):
        event = event_after(rows, event_id='evt_' + str(index) * 32)
        path = tmp_path / f'event{index}.json'
        path.write_text(json.dumps([event]))
        files.append(path)
    processes = [subprocess.Popen([sys.executable, str(MODULE), 'append', '--store', str(store.root), '--records', str(path)],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for path in files]
    answers = [process.communicate(timeout=20) for process in processes]
    assert sorted(process.returncode for process in processes) == [0, 1], answers
    recovered = j.Journal(store.root)
    assert len(recovered.records()) == 5
    assert len(recovered.outbox()['pending']) == 5
    assert [r['sequence'] for r in recovered.history(rows[1]['work_item_id'])['events']] == [1, 2]


def test_changed_identity_gap_and_duplicate_input_refuse_atomically(store):
    rows = fixtures.history()
    store.append(rows)
    changed = copy.deepcopy(rows[1])
    changed['objective'] = 'Changed without a new revision'
    with pytest.raises(ValueError): store.append([changed])
    with pytest.raises(ValueError): store.append([rows[0], rows[0]])
    with pytest.raises(ValueError): store.append([event_after(rows, sequence=3)])
    assert len(store.records()) == 4
    assert len(store.outbox()['pending']) == 4


def test_work_revision_and_event_correction_preserve_old_evidence(store):
    rows = fixtures.history()
    store.append(rows)
    terminal = event_after(rows, event_type='attempt.finished', outcome='failed')
    store.append([terminal])
    assert store.status()['work_items'][0]['attempts'][0]['terminal_claim']['outcome'] == 'failed'
    correction = event_after(rows, event_id='evt_' + 'e' * 32, sequence=3,
        previous_event_sha256=j.digest(j.encoded(terminal)), event_type='recovery.recorded',
        outcome='uncertain', corrects_event_id=terminal['event_id'])
    store.append([correction])
    assert store.status()['work_items'][0]['attempts'][0]['state'] == 'unfinished'
    history = store.history(rows[1]['work_item_id'])
    assert len(history['events']) == 3
    assert history['events'][-1]['corrects_event_id'] == terminal['event_id']
    work = copy.deepcopy(rows[1])
    work.update(revision=2, supersedes_sha256=j.digest(j.encoded(rows[1])), objective='Revised scope')
    store.append([work])
    assert store.status()['work_items'][0]['revision'] == 2
    assert len(store.records()) == 7


def test_interactive_import_has_explicit_origin_and_cannot_claim_observation(store):
    rows = fixtures.history()
    store.append(rows, interactive_import=True)
    history = store.history(rows[1]['work_item_id'])
    assert history['events'][0]['ingestion'] == 'interactive_import'
    assert history['events'][0]['provenance'] == 'imported'
    event = event_after(rows)
    event['provenance']['kind'] = 'observed'
    with pytest.raises(ValueError): store.append([event], interactive_import=True)
    with pytest.raises(ValueError): store.append(fixtures.history('library-managed.json'), interactive_import=True)
    assert len(store.records()) == 4


def test_two_repositories_unfinished_failed_and_release_stages_are_distinct(store):
    one, two = fixtures.history(), fixtures.history('library-managed.json')
    store.append(one + two)
    assert len(store.status()['work_items']) == 2
    assert len(store.status(repository_id='jarvis')['work_items']) == 1
    assert store.status(repository_id='jarvis')['work_items'][0]['attempts'][0]['state'] == 'unfinished'
    events = []
    prior = one[-1]
    for index, kind in enumerate(('attempt.finished', 'validation.finished', 'branch.published', 'change.merged', 'release.deployed', 'release.verified', 'decision.recorded'), 2):
        event = copy.deepcopy(prior)
        event.update(event_id='evt_' + f'{index:032x}', sequence=index,
            previous_event_sha256=j.digest(j.encoded(prior)), event_type=kind,
            outcome='approved' if kind == 'decision.recorded' else 'succeeded',
            decision_subject='deliverable_acceptance' if kind == 'decision.recorded' else None)
        events.append(event)
        prior = event
    store.append(events)
    summary = store.summary(one[1]['work_item_id'])
    assert summary['release_status'] == 'not_inferred'
    assert {r['stage'] for r in summary['facts']} >= {'execution', 'validation', 'publication', 'merge', 'deployment', 'verification', 'human_decisions'}
    assert all(r['provenance'] == 'imported' for r in summary['facts'])


def test_jarvis_projection_excludes_private_strings_references_and_artifacts(store, tmp_path):
    rows = fixtures.history()
    rows[-1]['summary'] = 'PRIVATE_EVENT_TEXT'
    rows[-1]['references'] = [{'namespace': 'external', 'id': 'PRIVATE_REFERENCE'}]
    event, sha, raw = artifact_event(rows)
    event['summary'] = 'PRIVATE_EVENT_TEXT'
    store.append(rows + [event], {sha: raw})
    target = tmp_path / 'projection'
    target.mkdir(mode=0o700)
    view = target / 'jarvis.json'
    store.publish_jarvis(view, rows[1]['work_item_id'])
    encoded_view = view.read_text()
    for private in ('PRIVATE_EVENT_TEXT', 'PRIVATE_REFERENCE', 'operator_only', 'art_' + '1' * 32,
                    rows[1]['objective'], '/srv/git', raw.decode()):
        assert private not in encoded_view
    assert j.read_projection(view)['audience'] == 'jarvis'
    assert view.stat().st_mode & 0o777 == 0o440
    assert store.history(rows[1]['work_item_id'])['events'][0]['summary'] == 'PRIVATE_EVENT_TEXT'
    assert store.artifact(sha) == raw


def test_shared_artifact_projects_reference_only_not_bytes(store, tmp_path):
    rows = fixtures.history()
    event, sha, raw = artifact_event(rows)
    event['artifacts'][0]['visibility'] = 'operator_and_jarvis'
    store.append(rows + [event], {sha: raw})
    shared = store.summary(rows[1]['work_item_id'], audience='jarvis')
    assert shared['facts'][-1]['artifacts'] == [{'artifact_id': 'art_' + '1' * 32, 'sha256': sha, 'purpose': 'validation'}]
    assert raw.decode() not in json.dumps(shared)


def test_projection_rejects_unknown_fields_and_never_opens_private_store(store, tmp_path):
    rows = fixtures.history()
    store.append(rows)
    directory = tmp_path / 'views'
    directory.mkdir(mode=0o700)
    path = directory / 'view.json'
    store.publish_jarvis(path, rows[1]['work_item_id'])
    value = j.read_projection(path)
    value['summary']['facts'][0]['raw_log'] = 'PRIVATE'
    path.chmod(0o600)
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError): j.read_projection(path)
    with pytest.raises(ValueError): store.publish_jarvis(store.root / 'view.json', rows[1]['work_item_id'])


def test_projection_atomic_replacement_preserves_previous_on_failure(store, tmp_path):
    rows = fixtures.history()
    store.append(rows)
    directory = tmp_path / 'views'
    directory.mkdir(mode=0o700)
    path = directory / 'view.json'
    store.publish_jarvis(path, rows[1]['work_item_id'])
    previous = path.read_bytes()
    store.append([event_after(rows)])
    with patch.object(j.os, 'replace', side_effect=OSError('fixture replace failure')):
        with pytest.raises(OSError): store.publish_jarvis(path, rows[1]['work_item_id'])
    assert path.read_bytes() == previous
    assert list(directory.iterdir()) == [path]


def test_artifact_missing_mismatch_and_metadata_reclassification_refused(store):
    rows = fixtures.history()
    event, sha, raw = artifact_event(rows)
    with pytest.raises(ValueError): store.append(rows + [event])
    with pytest.raises(ValueError): store.append(rows + [event], {sha: b'wrong'})
    store.append(rows + [event], {sha: raw})
    changed = copy.deepcopy(event)
    changed.update(event_id='evt_' + 'e' * 32, sequence=3, previous_event_sha256=j.digest(j.encoded(event)))
    changed['artifacts'][0]['visibility'] = 'operator_and_jarvis'
    with pytest.raises(ValueError): store.append([changed])
    assert store.artifact(sha) == raw


@pytest.mark.parametrize('offset,limit', [(-1,1), (0,0), (0,101), (True,1), (0,True)])
def test_pagination_refuses_unbounded_or_boolean_arguments(store, offset, limit):
    with pytest.raises(ValueError): store.status(offset=offset, limit=limit)
    with pytest.raises(ValueError): store.history('wrk_' + '1' * 32, after=offset, limit=limit)


def test_pagination_keeps_event_sequence_cursor(store):
    rows = fixtures.history()
    store.append(rows + [event_after(rows)])
    first = store.history(rows[1]['work_item_id'], limit=1)
    assert first['has_more'] and first['next_after'] == 1
    second = store.history(rows[1]['work_item_id'], after=first['next_after'], limit=1)
    assert not second['has_more'] and second['events'][0]['sequence'] == 2


def test_sql_triggers_reject_mutation_and_store_permissions_fail_closed(store):
    store.append(fixtures.history())
    with store.connection() as db:
        for sql in ('DELETE FROM records', "UPDATE records SET body=x'00'"):
            with pytest.raises(sqlite3.IntegrityError): db.execute(sql)
    store.path.chmod(0o640)
    with pytest.raises(ValueError): j.Journal(store.root)
    store.path.chmod(0o600)
    store.root.chmod(0o750)
    with pytest.raises(ValueError): j.Journal(store.root)


def test_symlink_store_and_duplicate_json_keys_refused(store, tmp_path):
    alias = tmp_path / 'alias'
    alias.symlink_to(store.root, target_is_directory=True)
    with pytest.raises(ValueError): j.Journal(alias)
    source = tmp_path / 'bad.json'
    source.write_text('{"schema_version":1,"schema_version":1}')
    with pytest.raises(ValueError): j.load_json(source)


def test_cli_errors_do_not_echo_private_input(store, tmp_path):
    source = tmp_path / 'private.json'
    source.write_text('[{"private":"DO_NOT_ECHO_THIS"}]')
    result = run_cli('append', '--store', store.root, '--records', source)
    assert result.returncode == 1
    assert 'DO_NOT_ECHO_THIS' not in result.stderr + result.stdout
    assert 'Traceback' not in result.stderr


def test_publication_refuses_to_replace_unrelated_private_files(store, tmp_path):
    rows = fixtures.history()
    store.append(rows)
    directory = tmp_path / 'private-output'
    directory.mkdir(mode=0o700)
    target = directory / 'existing-file'
    target.write_text('PRESERVE_UNRELATED_PRIVATE_FILE')
    with pytest.raises(ValueError): store.publish_jarvis(target, rows[1]['work_item_id'])
    assert target.read_text() == 'PRESERVE_UNRELATED_PRIVATE_FILE'


def test_stored_record_corruption_is_detected_before_projection(store):
    store.append(fixtures.history())
    with store.connection() as db:
        db.execute('DROP TRIGGER records_no_update')
        db.execute('UPDATE records SET body=? WHERE kind=?', (b'{}', 'event'))
    with pytest.raises(ValueError): store.records()
    with pytest.raises(ValueError): store.summary('wrk_' + '0' * 31 + '1', audience='jarvis')
