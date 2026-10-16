import importlib.util,json
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('publication',ROOT/'tools/rras_native/publication_policy.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class PublicationPolicyTests(unittest.TestCase):
    def setUp(self):
        self.p=json.loads((ROOT/'config/publication-policy.json').read_text())
        self.e=dict(worker_stop_verified=True,host_stop_verified=True,scope_verified=True,task_success=True,validation_exit=0)
    def plan(self,branch='codex/task-one',**options):return m.plan(self.p,'robot_ws',branch,'codex/task-one',**(self.e|options))
    def test_standing_push_and_draft_pr_without_merge_authority(self):
        for action in ('push','draft_pr'):
            result=self.plan(action=action);self.assertFalse(result['human_publication_confirmation_required']);self.assertFalse(result['merge_authorized']);self.assertFalse(result['deploy_authorized'])
            self.assertEqual(result['refspec'],'HEAD:refs/heads/codex/task-one')
    def test_default_other_branch_tags_and_refspecs_refused(self):
        for branch in ('main','master','codex/another-task','refs/tags/v1','codex/a:main','codex/../main','codex/-f'):
            with self.assertRaises(ValueError):self.plan(branch)
    def test_merge_deploy_force_delete_refused(self):
        for options in ({'action':'merge'},{'action':'deploy'},{'force':True},{'delete':True}):
            with self.assertRaises(ValueError):self.plan(**options)
    def test_failed_or_unknown_evidence_refused(self):
        for key,value in [('worker_stop_verified',False),('host_stop_verified',False),('scope_verified',False),('task_success',False),('validation_exit',1),('validation_exit',False)]:
            with self.assertRaises(ValueError):self.plan(**{key:value})
    def test_unadmitted_repository_refused(self):
        with self.assertRaises(ValueError):m.plan(self.p,'other','codex/task-one','codex/task-one',**self.e)
