import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('intake', Path(__file__).resolve().parents[1] / 'tools/rras_native/intake.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.policy = self.root/'policy.json'
        self.proposal = self.root/'proposal.json'
        self.p = {'schema_version':1,'identities':{'operator':['robot_ws']},'repositories':{
            'robot_ws':{'enabled':True,'allowed_paths':['node.py'],
                        'validations':{'unit':['/usr/bin/python3','-m','unittest']},
                        'worker_timeout_seconds':300,'validation_timeout_seconds':60}}}
        self.q = {'task_id':'TASK-one','repository_id':'robot_ws','objective':'Fix manual velocity',
                  'allowed_paths':['node.py'],'validation_id':'unit'}
    def submit(self, identity='operator'):
        self.policy.write_text(json.dumps(self.p))
        self.proposal.write_text(json.dumps(self.q))
        return m.prepare(self.policy,self.proposal,self.root/'state',authenticated_identity=identity)
    def test_compatible_request_and_no_execution_authority(self):
        result=self.submit();receipt=json.loads(Path(result['path']).read_text())
        self.assertEqual(m.local('manual_runner').validate_request(receipt['request']),receipt['request'])
        self.assertFalse(receipt['execution_authorized']);self.assertFalse(receipt['publication_authorized'])
        self.assertEqual(result['status'],'pending_operator_review')
    def test_duplicate_maps_same_receipt(self):
        first=self.submit();self.assertEqual(first,self.submit())
        self.assertEqual(len(list((self.root/'state').iterdir())),1)
    def test_unauthorized_identity_and_repository(self):
        with self.assertRaises(ValueError):self.submit('intruder')
        self.p['identities']['operator']=[]
        with self.assertRaises(ValueError):self.submit()
        self.assertFalse((self.root/'state').exists())
    def test_model_cannot_supply_identity_or_validation_command(self):
        for name,value in [('identity','operator'),('validation_argv',['/bin/sh'])]:
            self.q[name]=value
            with self.assertRaises(ValueError):self.submit()
            del self.q[name]
    def test_scope_and_unknown_validation_refused(self):
        self.q['allowed_paths']=['outside.py']
        with self.assertRaises(ValueError):self.submit()
        self.q['allowed_paths']=['node.py'];self.q['validation_id']='shell'
        with self.assertRaises(ValueError):self.submit()
    def test_changed_policy_changes_review_identity(self):
        first=self.submit();self.p['repositories']['robot_ws']['worker_timeout_seconds']=200
        self.assertNotEqual(first['submission_id'],self.submit()['submission_id'])
    def test_existing_receipt_tamper_preserved(self):
        result=self.submit();p=Path(result['path']);p.write_text('tampered')
        with self.assertRaises(ValueError):self.submit()
        self.assertEqual(p.read_text(),'tampered')

class HermesToolTests(unittest.TestCase):
    setUp = IntakeTests.setUp
    def tools(self):
        self.policy.write_text(json.dumps(self.p))
        class Server:
            def __init__(self): self.tools={}
            def tool(self):
                def decorate(fn): self.tools[fn.__name__]=fn;return fn
                return decorate
        server=Server()
        spec=importlib.util.spec_from_file_location('hermes_tools',Path(m.__file__).with_name('hermes_tools.py'))
        adapter=importlib.util.module_from_spec(spec);spec.loader.exec_module(adapter)
        self.identity='operator'
        adapter.register(server,policy=self.policy,state=self.root/'state',authenticated_identity=lambda:self.identity)
        return server.tools
    def test_chat_preparation_and_readback_without_launch(self):
        tools=self.tools();result=tools['prepare_coding_task'](**self.q)
        receipt=tools['coding_task_proposal'](result['submission_id'])
        self.assertFalse(receipt['execution_authorized']);self.assertFalse(receipt['publication_authorized'])
        self.assertNotIn('path',result)
    def test_cross_identity_and_revocation_refused(self):
        tools=self.tools();result=tools['prepare_coding_task'](**self.q)
        self.identity='other'
        with self.assertRaises(ValueError):tools['coding_task_proposal'](result['submission_id'])
        self.identity='operator';self.p['identities']['operator']=[];self.policy.write_text(json.dumps(self.p))
        with self.assertRaises(ValueError):tools['coding_task_proposal'](result['submission_id'])
    def test_traversal_refused(self):
        tools=self.tools()
        with self.assertRaises(ValueError):tools['coding_task_proposal']('../outside')
