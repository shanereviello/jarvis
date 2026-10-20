import copy
import importlib.util
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_repository_admission as fixtures

ROOT = Path(__file__).resolve().parents[1] / 'tools/rras_native'
spec = importlib.util.spec_from_file_location('operator_control', ROOT / 'operator_control.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class OperatorTests(unittest.TestCase):
    git = fixtures.AdmissionTests.git
    bind = fixtures.AdmissionTests.bind

    def setUp(self):
        fixtures.AdmissionTests.setUp(self)
        self.a = m.local('activity')
        self.l = m.local('approved_launch')
        self.approval = m.local('approval')
        self.admission = m.local('repository_admission')
        self.state = self.a.private_dir(self.root / 'state')
        self.proposals = self.a.private_dir(self.root / 'proposals')
        self.profile, self.codex = self.root / 'profile.json', self.root / 'codex.toml'
        self.profile.write_text('{}')
        self.codex.write_text('sandbox_mode="workspace-write"\n')
        self.config = {'schema_version': 1, 'registration': self.registration,
                       'hermes_project': 'engineering', 'profile': str(self.profile),
                       'codex_config': str(self.codex)}
        self.config_path = self.root / 'operator.json'
        self.save_config()
        self.jobs, self.workers = self.root / 'jobs', self.root / 'workers'
        self.jobs.mkdir()
        self.workers.mkdir(mode=0o700)
        self.credential = self.root / 'credential'
        self.credential.write_text('harmless fixture; not a provider credential')
        self.credential.chmod(0o600)
        for patcher in (patch.object(m, 'trusted', side_effect=lambda p: Path(p)),
                        patch.object(m, 'require_operator', side_effect=lambda p: self.a.private_dir(p))):
            patcher.start()
            self.addCleanup(patcher.stop)
        real_local = m.local
        patcher = patch.object(m, 'local', side_effect=lambda name: self.l if name == 'approved_launch' else real_local(name))
        patcher.start()
        self.addCleanup(patcher.stop)
        real_launch_local = self.l.local
        patcher = patch.object(self.l, 'local', side_effect=lambda name: m if name == 'operator_control' else real_launch_local(name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def save_config(self):
        self.config_path.write_text(json.dumps(self.config))

    def candidate(self):
        snapshot = self.admission.compile_snapshot(self.registration, self.work, 'engineering')
        raw = self.a.encoded(snapshot)
        candidate_id = self.a.digest(raw)
        self.a.absent(self.proposals / (candidate_id + '.admission.json'), raw)
        return candidate_id

    def capture(self):
        return m.capture(self.config_path, self.proposals, self.candidate(), self.state, 'codex/fixture')

    def approve(self, review_id):
        # Identity is mocked only for creating the approval; no root service call.
        with patch.object(m.os, 'getuid', return_value=0):
            # require_operator is already a fixture-only filesystem adapter.
            with patch.object(m, 'require_operator', return_value=self.state):
                return m.approve(self.state, review_id, self.config_path, approve_one_execution=True)

    def invoke(self, authorization_id, fail=False):
        calls = []
        def command(argv, timeout=30):
            calls.append(argv)
            if argv[0] == '/usr/bin/systemctl':
                return SimpleNamespace(returncode=0, stdout='not-found', stderr='')
            if argv[0] == '/usr/bin/pgrep':
                return SimpleNamespace(returncode=1, stdout='', stderr='')
            if fail:
                raise TimeoutError('fixture lost response')
            return SimpleNamespace(returncode=0, stdout='fixture only; no worker', stderr='')
        with patch.object(self.l, 'trusted', side_effect=lambda p: Path(p)), \
             patch.object(self.l, 'worker_root', return_value=self.workers), \
             patch.object(self.l.pwd, 'getpwnam', return_value=SimpleNamespace(pw_name='fixture', pw_uid=996, pw_gid=996)), \
             patch.object(self.l.os, 'getgrouplist', return_value=[996]), \
             patch.object(self.l.os, 'chown'), patch.object(self.l, 'command', side_effect=command):
            result = m.launch(self.state, authorization_id, self.config_path, self.jobs, self.workers, self.credential)
        return result, calls

    def assert_unconsumed(self, auth_id):
        self.assertFalse((self.state / (auth_id + '.consumed.json')).exists())
        self.assertEqual(list(self.jobs.iterdir()), [])

    def test_capture_review_approve_launch_and_evidence(self):
        captured = self.capture()
        self.assertEqual(captured, self.capture())
        view = m.review(self.state, captured['review_id'], self.config_path)
        self.assertFalse(view['execution_authorized'])
        self.assertNotIn('profile', view)
        self.assertEqual(view['request']['objective'], self.work['objective'])
        auth = self.approve(captured['review_id'])
        before = m.evidence(self.state, auth['authorization_id'])
        self.assertEqual(before['state'], 'approved_not_consumed')
        result, calls = self.invoke(auth['authorization_id'])
        self.assertTrue(result['host_stop_verified'])
        after = m.evidence(self.state, auth['authorization_id'])
        self.assertEqual(after['state'], 'service_returned')
        self.assertFalse(after['task_success_established'])
        self.assertFalse(after['publication_authorized'])
        self.assertNotIn('job', after)
        self.assertEqual(len([c for c in calls if c[0] == '/usr/bin/systemd-run']), 1)
        with self.assertRaises(FileExistsError): self.invoke(auth['authorization_id'])

    def test_two_repositories_same_capture_interface(self):
        one = self.capture()
        self.invoke(self.approve(one['review_id'])['authorization_id'])
        other = self.root / 'another-repo'
        subprocess.run(['git', 'clone', '--quiet', str(self.repo), str(other)], check=True)
        self.registration['source']['canonical_path'] = str(other)
        self.registration['registration_id'] = 'reg_' + '3' * 32
        self.registration['repository_id'] = 'another_repository'
        self.work['work_item_id'] = 'wrk_' + '3' * 32
        self.work['objective'] = 'A distinct bounded correction in another repository.'
        self.work['repository_id'] = 'another_repository'
        self.bind()
        self.save_config()
        two = self.capture()
        self.assertNotEqual(one['review_id'], two['review_id'])
        self.assertEqual(two['review']['request']['repository_id'], 'another_repository')
        result, _ = self.invoke(self.approve(two['review_id'])['authorization_id'])
        self.assertTrue(result['host_stop_verified'])
        self.assertEqual(len(list(self.jobs.iterdir())), 2)

    def test_edited_candidate_does_not_mutate_immutable_review(self):
        captured = self.capture()
        self.work['objective'] = 'Changed proposal later'
        self.candidate()
        self.assertEqual(m.review(self.state, captured['review_id'], self.config_path)['request']['objective'],
                         'Prepare a bounded unit-test correction.')

    def test_unadmitted_candidate_recipe_and_project_refused(self):
        self.registration['validation_recipes'][0]['argv'] = ['/bin/false']
        self.bind()
        with self.assertRaises(ValueError): self.capture()
        self.save_config()
        snapshot = self.admission.compile_snapshot(self.registration, self.work, 'different_project')
        raw = self.a.encoded(snapshot)
        candidate_id = self.a.digest(raw)
        self.a.absent(self.proposals / (candidate_id + '.admission.json'), raw)
        with self.assertRaises(ValueError):
            m.capture(self.config_path, self.proposals, candidate_id, self.state, 'codex/fixture')

    def test_changed_live_registration_revokes_approval(self):
        captured = self.capture()
        auth = self.approve(captured['review_id'])
        self.registration['path_policy']['allowed_roots'] = ['docs']
        self.save_config()
        with self.assertRaises(ValueError): self.invoke(auth['authorization_id'])
        self.assert_unconsumed(auth['authorization_id'])
        with self.assertRaises(ValueError): self.approve(captured['review_id'])

    def test_moved_baseline_refuses_before_approval_or_consumption(self):
        captured = self.capture()
        auth = self.approve(captured['review_id'])
        (self.repo / 'src/library.py').write_text('changed\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'moved')
        with self.assertRaises(ValueError): self.invoke(auth['authorization_id'])
        self.assert_unconsumed(auth['authorization_id'])
        with self.assertRaises(ValueError): self.approve(captured['review_id'])

    def test_changed_session_or_control_code_refused_before_consumption(self):
        captured = self.capture()
        auth = self.approve(captured['review_id'])
        with patch.object(m, 'control_hashes', return_value={}):
            with self.assertRaises(ValueError): self.invoke(auth['authorization_id'])
        self.assert_unconsumed(auth['authorization_id'])
        self.profile.write_text('{"changed":true}')
        with self.assertRaises(ValueError): self.invoke(auth['authorization_id'])
        self.assert_unconsumed(auth['authorization_id'])

    def test_explicit_approval_flag_and_review_branch_required(self):
        captured = self.capture()
        with self.assertRaises(ValueError): m.approve(self.state, captured['review_id'], self.config_path)
        for branch in ('main', 'codex/nested/branch', 'codex/with.dot'):
            with self.assertRaises(ValueError):
                m.capture(self.config_path, self.proposals, self.candidate(), self.state, branch)

    def test_configuration_duplicate_unknown_fields_and_replacement_refused(self):
        captured = self.capture()
        for text in ('{"schema_version":1,"schema_version":1}', json.dumps({**self.config, 'enabled': True})):
            self.config_path.write_text(text)
            with self.assertRaises(ValueError): m.review(self.state, captured['review_id'], self.config_path)
        self.save_config()
        other = self.root / 'other.json'
        other.write_bytes(self.config_path.read_bytes())
        with self.assertRaises(ValueError): m.review(self.state, captured['review_id'], other)

    def test_forged_review_association_detected_even_with_new_digest(self):
        captured = self.capture()
        record = copy.deepcopy(captured['review'])
        record['request']['allowed_paths'] = ['src/other.py']
        with self.assertRaises(ValueError): m.validate_review(record, self.config_path)
        record = copy.deepcopy(captured['review'])
        record['admission']['control_files'] = {}
        with self.assertRaises(ValueError): m.validate_review(record, self.config_path)

    def test_lost_service_response_and_missing_or_mixed_evidence(self):
        auth = self.approve(self.capture()['review_id'])
        with self.assertRaises(TimeoutError): self.invoke(auth['authorization_id'], fail=True)
        summary = m.evidence(self.state, auth['authorization_id'])
        self.assertEqual(summary['state'], 'launch_recorded')
        self.assertFalse(summary['task_success_established'])
        with self.assertRaises(FileExistsError): self.invoke(auth['authorization_id'])
        consumed = self.state / (auth['authorization_id'] + '.consumed.json')
        consumed.unlink()
        with self.assertRaises(ValueError): m.evidence(self.state, auth['authorization_id'])

    def test_busy_global_slot_refuses_without_consuming_approval(self):
        auth = self.approve(self.capture()['review_id'])
        with patch.object(self.l, 'slot', side_effect=ValueError('slot busy')):
            with self.assertRaisesRegex(ValueError, 'slot busy'):
                self.invoke(auth['authorization_id'])
        self.assert_unconsumed(auth['authorization_id'])

    def test_missing_or_cross_linked_evidence_never_claims_success(self):
        auth = self.approve(self.capture()['review_id'])
        row = {'authorization_id': auth['authorization_id'], 'review_id': '0' * 64}
        self.a.absent(self.state / (auth['authorization_id'] + '.consumed.json'), self.a.encoded(row))
        with self.assertRaises(ValueError): m.evidence(self.state, auth['authorization_id'])

    def test_launcher_itself_checks_admission_before_consumption(self):
        auth = self.approve(self.capture()['review_id'])
        # Bypass operator wrapper to prove the underlying launcher calls the guard.
        with patch.object(m, 'validate_review', side_effect=ValueError('guard called')) as guard, \
             patch.object(self.l, 'trusted', side_effect=lambda p: Path(p)), \
             patch.object(self.l, 'worker_root', return_value=self.workers), \
             patch.object(self.l.pwd, 'getpwnam', return_value=SimpleNamespace(pw_name='fixture', pw_uid=996, pw_gid=996)), \
             patch.object(self.l.os, 'getgrouplist', return_value=[996]), patch.object(self.l, 'slot'):
            with self.assertRaisesRegex(ValueError, 'guard called'):
                self.l.launch(self.state, auth['authorization_id'], self.jobs, self.workers, self.config_path, self.credential)
        guard.assert_called_once()
        self.assert_unconsumed(auth['authorization_id'])


class ProtectedBoundaryTests(unittest.TestCase):
    def test_relative_protected_paths_refused(self):
        for path in ('state', '.', '../configuration.json'):
            with self.assertRaises(ValueError): m.trusted(path)

    def test_root_identity_cannot_use_user_writable_source_installation(self):
        with patch.object(m.os, 'getuid', return_value=0), patch.object(m.os, 'geteuid', return_value=0):
            with self.assertRaises(ValueError): m.require_operator('/tmp')

    def test_unprivileged_cli_cannot_enter_operator_boundary(self):
        # Real boundary: no ownership/trusted-path adapter here.
        with patch.object(m.os, 'getuid', return_value=1000), patch.object(m.os, 'geteuid', return_value=1000):
            with self.assertRaises(ValueError): m.require_operator('/nonexistent')


if __name__ == '__main__':
    unittest.main()
