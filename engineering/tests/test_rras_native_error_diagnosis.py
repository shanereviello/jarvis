import importlib.util
import json
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('diagnostic',Path(__file__).resolve().parents[1]/'tools/rras_native/diagnose_canary_errors.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class DiagnosisTests(unittest.TestCase):
    def test_billing_code_separate_from_general_type(self):
        s,t=m.classify(json.dumps({'error':{'type':'insufficient_quota','code':'credit_balance_exhausted','message':'PRIVATE-FIXTURE'}}))
        self.assertEqual(s['credit_balance_exhausted'],1)
        self.assertNotIn('PRIVATE-FIXTURE',str((s,t)))

    def test_mentions_do_not_become_structured_evidence(self):
        s,t=m.classify('example insufficient_quota or rate_limit_exceeded')
        self.assertFalse(s)
        self.assertEqual(t['rate_limit_exceeded'],1)

    def test_unknown_codes_and_credentials_never_emitted(self):
        s,t=m.classify(json.dumps({'error':{'code':'PRIVATE-FIXTURE','message':'Authorization: SECRET-FIXTURE'}}))
        self.assertFalse(s);self.assertFalse(t)

    def test_embedded_error_body_is_parsed(self):
        s,t=m.classify(json.dumps({'message':json.dumps({'error':{'code':'project_spend_limit_exceeded'}})}))
        self.assertEqual(s['project_spend_limit_exceeded'],1)
