import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('host', ROOT / 'tools/rras_native/prepare_host.py')
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)
spec = importlib.util.spec_from_file_location('dispatcher_probe', ROOT / 'tools/rras_native/probe_dispatcher.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)

spec = importlib.util.spec_from_file_location('identity_probe', ROOT / 'tools/rras_native/probe_host_worker.py')
identity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(identity)

spec = importlib.util.spec_from_file_location('foreground_probe', ROOT / 'tools/rras_native/probe_foreground.py')
foreground = importlib.util.module_from_spec(spec)
spec.loader.exec_module(foreground)


class HostCandidateTests(unittest.TestCase):
    def test_foreground_readiness_and_clean_stop_are_both_required(self):
        for stop_code, expected in ((0,True),(-9,False)):
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                class FakeProcess:
                    pid=1234
                    returncode=None
                    def poll(self):return self.returncode
                    def terminate(self):
                        self.returncode=stop_code
                        with (root/'gateway.log').open('a') as f:f.write('Shutdown context: signal=SIGTERM\n')
                    def wait(self,timeout):return self.returncode
                def start(argv,**kwargs):
                    self.assertEqual(argv[1:],['gateway','run'])
                    self.assertNotIn('RRAS_OPENAI_API_KEY',kwargs['env'])
                    (root/'home/gateway_state.json').write_text(json.dumps({'pid':1234,'gateway_state':'running','platforms':{},'active_agents':0}))
                    return FakeProcess()
                with patch.object(foreground.tempfile,'mkdtemp',return_value=str(root)), patch.object(foreground.subprocess,'Popen',side_effect=start):
                    _,e=foreground.run(Path('/fixture/hermes'))
                self.assertEqual(e['success'],expected)
                self.assertTrue(e['stopped'])

    def test_pinned_native_sigterm_exit_one_is_not_forced_shutdown(self):
        self.assertTrue(foreground.shutdown_accepted(True,True,1,False,[],True))
        self.assertFalse(foreground.shutdown_accepted(True,True,1,True,[],True))
        self.assertFalse(foreground.shutdown_accepted(True,True,1,False,[123],True))
        self.assertFalse(foreground.shutdown_accepted(True,False,1,False,[],True))
        self.assertFalse(foreground.shutdown_accepted(True,True,1,False,[],False))

    def test_wrong_identity_cli_retains_machine_readable_failure_without_start(self):
        result=subprocess.run(['python3','-B',str(ROOT/'tools/rras_native/probe_host_worker.py'),
             '--uid','1000','--gid','1000','--protected-fixture','/unused',
             '--binary','/unused','--evidence','/unused'],capture_output=True,text=True)
        self.assertEqual(result.returncode,1)
        receipt=json.loads(result.stdout)
        self.assertFalse(receipt['success']);self.assertEqual(receipt['api_calls'],0)
        self.assertEqual(receipt['error_type'],'ValueError')
        self.assertNotIn('Traceback',result.stderr)

    def test_worker_rejects_operator_and_extra_groups(self):
        for uid in (0,1000,997,65534):
            with self.assertRaises(ValueError):identity.check_identity(uid,uid)
        with patch.object(identity.os,'getuid',return_value=1234), patch.object(identity.os,'geteuid',return_value=1234), patch.object(identity.os,'getgid',return_value=1234), patch.object(identity.os,'getgroups',return_value=[1234,999]):
            with self.assertRaises(ValueError):identity.check_identity(1234,1234)
        with patch.object(identity.os,'getuid',return_value=1234), patch.object(identity.os,'geteuid',return_value=1234), patch.object(identity.os,'getgid',return_value=1234), patch.object(identity.os,'getgroups',return_value=[1234]):
            identity.check_identity(1234,1234)

    def test_fixture_cleanup_does_not_adopt_reused_pid(self):
        with patch.object(Path, "read_bytes", return_value=b"python\0unrelated.py\0"):
            self.assertFalse(probe.owned_child(123, Path("/tmp/fixture")))
        with patch.object(Path, "read_bytes", return_value=b"python\0/tmp/fixture/fake_coding_child.py\0"):
            self.assertTrue(probe.owned_child(123, Path("/tmp/fixture")))
        with patch.object(Path, "read_bytes", side_effect=FileNotFoundError):
            self.assertFalse(probe.owned_child(123, Path("/tmp/fixture")))

    def test_zombie_is_not_a_live_worker(self):
        with patch.object(Path, "read_text", return_value="123 (fake coding child) Z 1 2"):
            self.assertFalse(probe.alive(123))
        with patch.object(Path, "read_text", return_value="123 (fake coding child) S 1 2"):
            self.assertTrue(probe.alive(123))

    def test_wrong_revision_rejected_before_destination_creation(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(host, 'git', return_value=b'wrong\n'):
            target = Path(tmp) / 'candidate'
            with self.assertRaises(ValueError):
                host.prepare(target, tmp, 'unused', 'candidate-model')
            self.assertFalse(target.exists())

    def test_source_pin_mismatch_rejected(self):
        with patch.object(host, 'git', side_effect=[host.REVISION.encode(), b'wrong bytes']):
            with self.assertRaises(ValueError):
                host.verify_source('fixture')

    def test_candidate_archives_committed_source_and_is_nonactivating(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'source'
            source.mkdir()
            subprocess.run(['git', 'init', '-q', str(source)], check=True)
            for name in host.PINS:
                p = source / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(b'committed fixture')
            subprocess.run(['git', '-C', str(source), 'add', '.'], check=True)
            subprocess.run(['git', '-C', str(source), '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                            'commit', '-qm', 'fixture'], check=True)
            revision = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
            (source / 'pyproject.toml').write_bytes(b'dirty local source must not be packaged')
            class Runtime:
                def prepare(self, destination, model, binary):
                    destination.mkdir()
                    (destination / 'profile').mkdir()
                    (destination / 'profile/config.yaml').write_text('{}')
                    for name in ['Dockerfile', 'container_probe.py', 'container_acceptance.py', 'manifest.json']:
                        (destination / name).write_text('old container fixture')
            # Only runtime software packaging is stubbed; git archive, pins, plan/unit/manifest are real.
            runtime = Runtime()
            fake_spec = type('Spec', (), {'loader': type('Loader', (), {'exec_module': lambda self, m: None})()})()
            pins = {name: hashlib.sha256(b'committed fixture').hexdigest() for name in host.PINS}
            with patch.object(host, 'REVISION', revision), patch.object(host, 'PINS', pins), \
                 patch.object(host.importlib.util, 'spec_from_file_location', return_value=fake_spec), \
                 patch.object(host.importlib.util, 'module_from_spec', return_value=runtime):
                target = root / 'candidate'
                manifest = host.prepare(target, source, 'fixture', 'candidate-model')
                self.assertEqual((target / 'pyproject.toml').read_bytes(), b'committed fixture')
                for name, pin in manifest['files'].items():
                    self.assertEqual(hashlib.sha256((target / name).read_bytes()).hexdigest(), pin)
                plan = json.loads((target / 'activation-plan.json').read_text())
                self.assertFalse(plan['installed'])
                self.assertFalse(plan['credentials_included'])
                self.assertFalse(plan['dependency_environment_built'])
                self.assertNotIn('Dockerfile', manifest['files'])
                unit = (target / 'rras-engineering-check.service').read_text()
                self.assertIn('hermes kanban --help', unit)
                self.assertNotIn('[Install]', unit)
                self.assertNotIn('EnvironmentFile', unit)
                self.assertIn('KillMode=control-group', unit)
                with self.assertRaises(ValueError):
                    host.prepare(target, source, 'fixture', 'candidate-model')


if __name__ == '__main__':
    unittest.main()
