import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]/'tools/rras_native'
spec=importlib.util.spec_from_file_location('acceptance',ROOT/'acceptance.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class AcceptanceTests(unittest.TestCase):
    def args(self,root,*extra):
        return m.parser().parse_args(['--case','manual','--source','/source','--python','/python','--work',str(root),*extra])
    def test_refuses_missing_policy_and_credentials_before_probe(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):m.run(self.args(folder))
            with patch.dict(os.environ,{'OPENAI_API_KEY':'harmless-fixture'}):
                with self.assertRaises(ValueError):m.run(self.args(folder,'--profile','/profile','--codex-config','/config'))
    def test_manual_delegates_to_existing_native_fixture(self):
        from types import SimpleNamespace
        calls=[]
        def probe(*args):calls.append(args);return {'success':True,'api_calls':0}
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{},clear=True),patch.object(m,'module',return_value=SimpleNamespace(run=probe)):
            result=m.run(self.args(folder,'--profile','/profile','--codex-config','/config','--dedicated-cgroup'))
            self.assertTrue(result['success']);self.assertTrue(calls[0][-1])
    def test_no_paid_or_execution_mode(self):
        with self.assertRaises(SystemExit):self.args('/tmp','--authorize-one-paid-task')
