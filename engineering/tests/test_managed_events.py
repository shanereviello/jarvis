"""Managed receipts to real disposable journal; service/ownership adapters only."""
import importlib.util
import os
import subprocess
import sys
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import test_operator_control as controls

m = controls.m


def module(name):
    spec = importlib.util.spec_from_file_location(name, controls.ROOT / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class ManagedTests(unittest.TestCase):
    git = controls.OperatorTests.git
    bind = controls.OperatorTests.bind
    save_config = controls.OperatorTests.save_config
    candidate = controls.OperatorTests.candidate
    capture = controls.OperatorTests.capture
    approve = controls.OperatorTests.approve
    invoke = controls.OperatorTests.invoke
    assert_unconsumed = controls.OperatorTests.assert_unconsumed

    def setUp(self):
        controls.OperatorTests.setUp(self)
        self.e, self.j = module('managed_events'), module('workflow_journal')
        # Existing fixture approval mocks root identity; keep the real disposable
        # journal's ownership checks tied to the actual test-process owner.
        actual_uid = os.getuid()
        class JournalOS:
            def getuid(self): return actual_uid
            def __getattr__(self, name): return getattr(os, name)
        self.j.os = JournalOS()
        journal_root = self.root / 'journal'
        journal_root.mkdir(mode=0o700)
        self.store = self.j.Journal(journal_root, create=True)
        self.config['journal'] = str(journal_root)
        self.save_config()
        original = m.local
        launch_original = self.l.local
        event_original = self.e.local
        for patcher in (
            patch.object(m, 'local', side_effect=lambda name: self.e if name == 'managed_events' else self.j if name == 'workflow_journal' else original(name)),
            patch.object(self.l, 'local', side_effect=lambda name: self.e if name == 'managed_events' else launch_original(name)),
            patch.object(self.e, 'local', side_effect=lambda name: m if name == 'operator_control' else self.j if name == 'workflow_journal' else event_original(name))):
            patcher.start()
            self.addCleanup(patcher.stop)

    def events(self):
        return [r for r, _ in self.store.records() if r['kind'] == 'event']

    def test_capture_approval_launch_are_recorded_once_and_never_claim_task_success(self):
        captured = self.capture()
        self.assertEqual(len(self.events()), 1)
        self.capture()
        self.assertEqual(len(self.events()), 1)
        auth = self.approve(captured['review_id'])
        result, _ = self.invoke(auth['authorization_id'])
        events = self.events()
        self.assertEqual(len(events), 5)
        self.assertEqual([e['sequence'] for e in events], [1, 2, 3, 4, 5])
        self.assertNotIn('attempt.finished', [e['event_type'] for e in events])
        self.assertTrue(all(e['provenance']['kind'] == 'observed' for e in events))
        self.assertEqual(self.store.status()['work_items'][0]['attempts'][0]['state'], 'unfinished')
        before = len(self.store.outbox()['pending'])
        m.reconcile(self.state, auth['authorization_id'])
        self.assertEqual(len(self.events()), 5)
        self.assertEqual(len(self.store.outbox()['pending']), before)
        self.assertTrue(result['host_stop_verified'])

    def test_journal_failure_before_consume_blocks_service_without_consuming(self):
        auth = self.approve(self.capture()['review_id'])
        with patch.object(self.e, 'before_launch', side_effect=OSError('fixture journal failure')):
            with self.assertRaises(OSError): self.invoke(auth['authorization_id'])
        self.assert_unconsumed(auth['authorization_id'])

    def test_failure_after_consume_retains_fence_and_reconciles_without_launch(self):
        auth = self.approve(self.capture()['review_id'])
        real_record = self.e.record
        def fail(review, review_id, phase, *args):
            if phase == 'consumed': raise OSError('fixture write failure')
            return real_record(review, review_id, phase, *args)
        with patch.object(self.e, 'record', side_effect=fail):
            # invoke installs its own fake command; phase failure still happens
            # before clone/staging/systemd-run. No production service is called.
            with self.assertRaises(OSError): self.invoke(auth['authorization_id'])
        self.assertTrue((self.state / (auth['authorization_id'] + '.consumed.json')).exists())
        self.assertEqual(list(self.jobs.iterdir()), [])
        with patch.object(self.l, 'command', side_effect=AssertionError('reconcile must not contact systemd')):
            answer = m.reconcile(self.state, auth['authorization_id'])
        self.assertFalse(answer['execution_retried'])
        self.assertEqual(len(self.events()), 3)
        self.assertEqual(len([r for r, _ in self.store.records() if r['kind'] == 'attempt']), 1)
        with self.assertRaises(FileExistsError): self.invoke(auth['authorization_id'])

    def test_lost_response_retains_unknown_attempt_and_never_retries(self):
        auth = self.approve(self.capture()['review_id'])
        with self.assertRaises(TimeoutError): self.invoke(auth['authorization_id'], fail=True)
        self.assertEqual(len(self.events()), 4)
        self.assertEqual(m.reconcile(self.state, auth['authorization_id'])['state'], 'launch_recorded')
        self.assertEqual(len(self.events()), 4)
        with self.assertRaises(FileExistsError): self.invoke(auth['authorization_id'])

    def test_result_journal_failure_can_be_repaired_from_protected_result(self):
        auth = self.approve(self.capture()['review_id'])
        real_record = self.e.record
        def fail(review, review_id, phase, *args):
            if phase == 'returned': raise OSError('fixture final write failure')
            return real_record(review, review_id, phase, *args)
        with patch.object(self.e, 'record', side_effect=fail):
            with self.assertRaises(OSError): self.invoke(auth['authorization_id'])
        self.assertEqual(len(self.events()), 4)
        m.reconcile(self.state, auth['authorization_id'])
        self.assertEqual(len(self.events()), 5)
        final = self.events()[-1]
        payload = self.store.artifact(final['artifacts'][0]['sha256'])
        self.assertNotIn(b'fixture service', payload)
        self.assertNotIn(b'/work', payload)

    def test_failed_capture_write_replays_without_duplicate_review(self):
        with patch.object(self.e, 'record', side_effect=OSError('fixture journal failure')):
            with self.assertRaises(OSError): self.capture()
        self.assertEqual(len(list(self.state.glob('*.review.json'))), 1)
        self.capture()
        self.assertEqual(len(self.events()), 1)
        self.assertEqual(len(list(self.state.glob('*.review.json'))), 1)

    def test_failed_approval_recording_retains_receipt_and_reconciles(self):
        captured = self.capture()
        with patch.object(self.e, 'record', side_effect=OSError('fixture journal failure')):
            with self.assertRaises(OSError): self.approve(captured['review_id'])
        files = list(self.state.glob('*.approval.json'))
        self.assertEqual(len(files), 1)
        auth_id = files[0].name.split('.')[0]
        self.assertEqual(len(self.events()), 1)
        m.reconcile(self.state, auth_id)
        self.assertEqual(len(self.events()), 2)
        self.assert_unconsumed(auth_id)

    def test_concurrent_transition_sequence_allocation_is_serialized(self):
        self.capture()
        event = self.events()[0]
        event = {k: v for k, v in event.items() if k not in {'schema_version', 'kind', 'sequence', 'previous_event_sha256', 'occurred_at', 'recorded_at'}}
        inputs = []
        for number in (1, 2):
            value = dict(event, event_id='evt_' + str(number) * 32)
            path = self.root / ('transition' + str(number) + '.json')
            path.write_text(json.dumps(value))
            inputs.append(path)
        script = "import importlib.util,sys;s=importlib.util.spec_from_file_location('j',sys.argv[1]);j=importlib.util.module_from_spec(s);s.loader.exec_module(j);j.Journal(sys.argv[2]).append([],transition=(j.load_json(sys.argv[3]),None))"
        processes = [subprocess.Popen([sys.executable, '-c', script, str(controls.ROOT / 'workflow_journal.py'), str(self.store.root), str(path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE) for path in inputs]
        answers = [p.communicate(timeout=15) for p in processes]
        self.assertEqual([p.returncode for p in processes], [0, 0], answers)
        self.assertEqual([e['sequence'] for e in self.events()], [1, 2, 3])

    def test_consumption_directory_sync_failure_prevents_service_and_preserves_fence(self):
        auth = self.approve(self.capture()['review_id'])
        approval = self.l.local('approval')
        activity = approval.local('activity')
        real_approval_local = approval.local
        real_launch_local = self.l.local
        with patch.object(activity, 'fsync_directory', side_effect=OSError('fixture directory sync failure')), \
             patch.object(approval, 'local', side_effect=lambda name: activity if name == 'activity' else real_approval_local(name)), \
             patch.object(self.l, 'local', side_effect=lambda name: approval if name == 'approval' else real_launch_local(name)):
            with self.assertRaises(OSError): self.invoke(auth['authorization_id'])
        self.assertTrue((self.state / (auth['authorization_id'] + '.consumed.json')).exists())
        self.assertEqual(list(self.jobs.iterdir()), [])
        m.reconcile(self.state, auth['authorization_id'])
        with self.assertRaises(FileExistsError): self.invoke(auth['authorization_id'])

    def test_transition_conflicts_are_refused_instead_of_rewritten(self):
        captured = self.capture()
        record = captured['review']
        self.e.record(record, captured['review_id'], 'captured')
        event = self.events()[0]
        changed = {k: v for k, v in event.items() if k not in {'schema_version', 'kind', 'sequence', 'previous_event_sha256', 'occurred_at', 'recorded_at'}}
        changed['summary'] = 'conflicting replay'
        with self.assertRaises(ValueError): self.store.append([], transition=(changed, None))
        self.assertEqual(len(self.events()), 1)


if __name__ == '__main__': unittest.main()
