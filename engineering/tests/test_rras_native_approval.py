import importlib.util,json,os
from pathlib import Path
import subprocess,tempfile,unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]/'tools/rras_native'
s=importlib.util.spec_from_file_location('approval',ROOT/'approval.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
a=m.local('activity')
class ApprovalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.repo=self.root/'repo';self.repo.mkdir()
        def git(*args):return subprocess.run(['git','-C',str(self.repo),*args],check=True,capture_output=True)
        git('init','-q');(self.repo/'code.py').write_text('value=0\n');git('add','.');git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','baseline')
        self.policy=self.root/'policy.json';self.p={'schema_version':1,'identities':{'hermes':['robot_ws']},'repositories':{'robot_ws':{'enabled':True,'allowed_paths':['code.py'],'validations':{'unit':['/usr/bin/python3','-m','unittest']},'worker_timeout_seconds':30,'validation_timeout_seconds':10}}};self.policy.write_text(json.dumps(self.p))
        self.registry=self.root/'registry.json';self.registry.write_text(json.dumps({'schema_version':1,'repositories':[{'repository_id':'robot_ws','path':str(self.repo),'enabled':True,'hermes_project':'robot-ws'}]}))
        self.proposals=self.root/'proposals';self.proposals.mkdir();self.state=self.root/'approvals'
        self.r={'schema_version':1,'task_id':'TASK-real','repository_id':'robot_ws','objective':'Fix value','allowed_paths':['code.py'],'validation_argv':['/usr/bin/python3','-m','unittest'],'worker_timeout_seconds':30,'validation_timeout_seconds':10,'commit_policy':'leave_uncommitted'}
        self.profile=self.root/'profile.json';self.profile.write_text('{}');self.codex=self.root/'config.toml';self.codex.write_text('sandbox_mode="workspace-write"')
        self.receipt={'schema_version':1,'authenticated_identity':'hermes','policy_sha256':a.digest(self.policy.read_bytes()),'request':self.r,'execution_authorized':False,'publication_authorized':False}
    def proposal(self):
        digest=a.digest(a.encoded(self.receipt));(self.proposals/(digest+'.json')).write_bytes(a.encoded(self.receipt));return digest
    def capture(self):return m.capture(self.proposals,self.proposal(),self.policy,self.registry,self.state,self.profile,self.codex)
    def test_capture_binds_exact_baseline_without_approving(self):
        result=self.capture();self.assertEqual(result,self.capture());self.assertFalse(result['review']['execution_authorized']);self.assertFalse(result['review']['publication_authorized'])
        self.assertEqual(len(list(self.state.iterdir())),1)
    def test_installation_fixture_cannot_execute(self):
        self.r['task_id']='TASK-preparation-acceptance-abc'
        with self.assertRaises(ValueError):self.capture()
    def test_policy_revocation_and_validation_expansion_refused(self):
        self.p['identities']['hermes']=[];self.policy.write_text(json.dumps(self.p))
        with self.assertRaises(ValueError):self.capture()
    def test_forged_argv_and_authority_refused(self):
        self.r['validation_argv']=['/bin/sh']
        with self.assertRaises(ValueError):self.capture()
        self.r['validation_argv']=['/usr/bin/python3','-m','unittest'];self.receipt['execution_authorized']=True
        with self.assertRaises(ValueError):self.capture()
    def test_dirty_canonical_refused(self):
        (self.repo/'code.py').write_text('dirty')
        with self.assertRaises(ValueError):self.capture()
    def test_mutable_proposal_does_not_change_review(self):
        result=self.capture();self.r['objective']='changed later';self.capture()
        self.assertEqual(m.read_review(self.state,result['review_id'])['request']['objective'],'Fix value')
    def test_approval_is_one_use_and_not_publication(self):
        result=self.capture();
        with patch.object(m.os,'getuid',return_value=0):approval=m.approve(self.state,result['review_id'])
        self.assertFalse(approval['publication_authorized'])
        self.assertEqual(m.consume(self.state,approval['authorization_id']),result['review'])
        with self.assertRaises(FileExistsError):m.consume(self.state,approval['authorization_id'])
    def test_review_tampering_blocks_approval(self):
        result=self.capture();(self.state/(result['review_id']+'.review.json')).write_text('{}')
        with self.assertRaises(ValueError):m.approve(self.state,result['review_id'])
