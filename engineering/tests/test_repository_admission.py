import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

TOOLS = Path(__file__).resolve().parents[1] / 'tools/rras_native'
spec = importlib.util.spec_from_file_location('repository_admission', TOOLS / 'repository_admission.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        self.git('init', '-b', 'main')
        self.git('config', 'user.name', 'Fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        (self.repo / 'src').mkdir()
        (self.repo / 'src/library.py').write_text('value = 1\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'fixture')
        fixtures = Path(__file__).resolve().parents[1] / 'contracts/examples/library-managed.json'
        self.registration, self.work = json.loads(fixtures.read_text())[:2]
        self.registration['source']['canonical_path'] = str(self.repo)
        self.work['baseline']['commit'] = self.git('rev-parse', 'HEAD').strip()
        self.bind()

    def git(self, *argv):
        return subprocess.run(['git', '-C', str(self.repo), *argv], check=True,
                              capture_output=True, text=True).stdout

    def bind(self):
        self.work['registration_sha256'] = m.local('workflow_records').record_digest(self.registration)

    def compile(self):
        return m.compile_snapshot(self.registration, self.work, 'engineering')

    def test_exact_translation_uses_existing_contract_and_no_authority(self):
        snapshot = self.compile()
        self.assertEqual(m.local('task_contract').validate_request(snapshot['request']), snapshot['request'])
        self.assertFalse(snapshot['execution_authorized'])
        self.assertFalse(snapshot['publication_authorized'])
        self.assertEqual(snapshot['request']['validation_argv'], self.registration['validation_recipes'][0]['argv'])
        self.assertEqual(m.inspect_repository(snapshot), {'baseline_verified': True, 'api_calls': 0})

    def test_two_repositories_same_commands_and_candidate_readback(self):
        first = self.root / 'first'
        for number, repo_id in enumerate(('example_library', 'second_library')):
            if number:
                other = self.root / 'other'
                subprocess.run(['git', 'clone', '--quiet', str(self.repo), str(other)], check=True)
                self.repo = other
                self.registration['repository_id'] = repo_id
                self.registration['source']['canonical_path'] = str(other)
                self.work['repository_id'] = repo_id
                self.work['objective'] = 'A different bounded correction.'
                self.bind()
            registration_path, work_path = self.root / 'registration.json', self.root / 'work.json'
            registration_path.write_text(json.dumps(self.registration))
            work_path.write_text(json.dumps(self.work))
            result = m.prepare(registration_path, work_path, 'engineering', first)
            self.assertEqual(result, m.prepare(registration_path, work_path, 'engineering', first))
            read = m.read_candidate(first, result['candidate_id'])
            self.assertEqual(read['repository_id'], repo_id)
            self.assertEqual(read['status'], 'pending_trusted_capture')
        self.assertEqual(len(list(first.iterdir())), 2)

    def test_wrong_exact_registration_and_repository_refused(self):
        self.registration['publication']['target_branch'] = 'release'
        with self.assertRaises(ValueError): self.compile()
        self.bind()
        self.work['repository_id'] = 'other'
        with self.assertRaises(ValueError): self.compile()

    def test_modes_and_unknown_recipe_refused(self):
        for mode in ('interactive', 'delegated'):
            self.work['mode'] = mode
            with self.assertRaises(ValueError): self.compile()
        self.work['mode'] = 'approval_driven'
        self.work['validation_id'] = 'unregistered'
        with self.assertRaises(ValueError): self.compile()

    def test_sha256_explicitly_unsupported_by_current_executor(self):
        self.registration['source']['object_format'] = 'sha256'
        self.bind()
        self.work['baseline']['commit'] = 'a' * 64
        with self.assertRaisesRegex(ValueError, 'SHA-1'): self.compile()

    def test_named_admitted_exact_baseline_required(self):
        for baseline in (None, {'ref': 'refs/heads/other', 'commit': 'a' * 40},
                         {'ref': 'refs/heads/main', 'commit': 'a' * 64}):
            self.work['baseline'] = baseline
            with self.assertRaises(ValueError): self.compile()

    def test_denied_paths_and_prefix_collisions(self):
        self.registration['path_policy']['denied_roots'].append('src/private')
        self.bind()
        for path in ('elsewhere.py', 'src/private/key', 'src/private', 'src',
                     'src/.git/config', 'src/.aws/config', 'src/.codex/config', 'src/AGENTS.md', 'src/RRAS_TASK.md'):
            self.work['requested_paths'] = [path]
            with self.assertRaises(ValueError, msg=path): self.compile()
        self.work['requested_paths'] = ['src/privateer.py']
        self.compile()

    def test_dot_root_still_obeys_denials(self):
        self.registration['path_policy']['allowed_roots'] = ['.']
        self.bind()
        self.work['requested_paths'] = ['README.md']
        self.compile()
        self.work['requested_paths'] = ['.git/config']
        with self.assertRaises(ValueError): self.compile()

    def test_dirty_and_moved_baseline_refused(self):
        snapshot = self.compile()
        (self.repo / 'src/library.py').write_text('dirty\n')
        with self.assertRaises(ValueError): m.inspect_repository(snapshot)
        self.git('add', '.')
        self.git('commit', '-qm', 'moved')
        with self.assertRaisesRegex(ValueError, 'baseline moved'): m.inspect_repository(snapshot)

    def test_directory_and_current_symlink_refused(self):
        self.work['requested_paths'] = ['src']
        with self.assertRaises(ValueError): m.inspect_repository(self.compile())
        self.work['requested_paths'] = ['src/link.py']
        (self.repo / 'src/link.py').symlink_to('library.py')
        self.git('add', '.')
        self.git('commit', '-qm', 'link')
        self.work['baseline']['commit'] = self.git('rev-parse', 'HEAD').strip()
        with self.assertRaises(ValueError): m.inspect_repository(self.compile())

    def test_selected_older_baseline_symlink_refused(self):
        (self.repo / 'src/old').symlink_to('/tmp')
        self.git('add', '.')
        self.git('commit', '-qm', 'old link')
        old = self.git('rev-parse', 'HEAD').strip()
        (self.repo / 'src/old').unlink()
        (self.repo / 'src/old').mkdir()
        (self.repo / 'src/old/file.py').write_text('safe\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'replace link')
        self.git('branch', 'reviewed', old)
        self.registration['baseline_refs'] = ['refs/heads/reviewed']
        self.bind()
        self.work['baseline'] = {'ref': 'refs/heads/reviewed', 'commit': old}
        self.work['requested_paths'] = ['src/old/file.py']
        with self.assertRaisesRegex(ValueError, 'baseline path'): m.inspect_repository(self.compile())

    def test_new_file_allowed_and_repository_alias_refused(self):
        self.work['requested_paths'] = ['src/new/module.py']
        m.inspect_repository(self.compile())
        alias = self.root / 'alias'
        alias.symlink_to(self.repo)
        self.registration['source']['canonical_path'] = str(alias)
        self.bind()
        with self.assertRaises(ValueError): m.inspect_repository(self.compile())

    def test_candidate_tamper_and_traversal_refused(self):
        state = m.local('activity').private_dir(self.root / 'state')
        snapshot = self.compile()
        snapshot['request']['validation_argv'] = ['/bin/false']
        raw = m.local('activity').encoded(snapshot)
        candidate_id = m.local('activity').digest(raw)
        (state / (candidate_id + '.admission.json')).write_bytes(raw)
        with self.assertRaisesRegex(ValueError, 'translation'): m.read_candidate(state, candidate_id)
        with self.assertRaises(ValueError): m.read_candidate(state, '../outside')

    def test_submodule_refused_without_executing_git_hooks(self):
        commit = self.git('rev-parse', 'HEAD').strip()
        (self.repo / 'src/vendor').mkdir()
        self.git('update-index', '--add', '--cacheinfo', '160000,' + commit + ',src/vendor')
        self.git('commit', '-qm', 'gitlink')
        self.work['baseline']['commit'] = self.git('rev-parse', 'HEAD').strip()
        self.work['requested_paths'] = ['src/vendor/module.py']
        with self.assertRaisesRegex(ValueError, 'submodule'):
            m.inspect_repository(self.compile())

    def test_jarvis_candidate_is_valid_bounded_and_not_enrolled(self):
        path = Path(__file__).resolve().parents[1] / 'config/jarvis-registration.candidate.json'
        row = json.loads(path.read_text())
        m.local('workflow_records').validate_record(row)
        self.assertEqual(row['repository_id'], 'jarvis')
        self.assertEqual(row['path_policy']['allowed_roots'], ['engineering/docs'])
        self.assertEqual(row['validation_recipes'][0]['argv'], ['/usr/bin/git', 'diff', '--check'])

    def test_candidate_changes_with_work_recipe_and_project(self):
        a = m.local('activity')
        original = a.digest(a.encoded(self.compile()))
        self.work['objective'] = 'Another exact objective'
        self.assertNotEqual(original, a.digest(a.encoded(self.compile())))
        self.registration['validation_recipes'][0]['timeout_seconds'] = 20
        self.bind()
        self.assertNotEqual(original, a.digest(a.encoded(self.compile())))
        one = self.compile()
        two = m.compile_snapshot(self.registration, self.work, 'different_project')
        self.assertNotEqual(a.digest(a.encoded(one)), a.digest(a.encoded(two)))


if __name__ == '__main__':
    unittest.main()
