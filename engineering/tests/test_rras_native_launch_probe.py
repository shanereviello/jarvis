import ast,importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
p=Path(__file__).resolve().parents[1]/'tools/rras_native/probe_approved_launch.py'
s=importlib.util.spec_from_file_location('probe',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class ProbeSafetyTests(unittest.TestCase):
    def test_real_runner_refused_before_any_host_action(self):
        with patch.object(m.os,'geteuid',return_value=0):
            with self.assertRaisesRegex(ValueError,'synthetic worker required'):m.run('/unused-control','/unused-jobs','/unused-workers')
    def test_synthetic_worker_uses_no_model_client_and_requires_sentinel(self):
        ast.parse(m.FAKE_WORKER)
        self.assertIn("m.delivered_key(a.credential)=='RRAS-APPROVAL-OFFLINE-FIXTURE'",m.FAKE_WORKER)
        self.assertNotIn('OpenAI',m.FAKE_WORKER);self.assertNotIn('requests',m.FAKE_WORKER)
        self.assertIn('os.getuid()==996',m.FAKE_WORKER)
