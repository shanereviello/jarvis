import importlib.util
from pathlib import Path
import unittest

p=Path(__file__).resolve().parents[1]/'tools/rras_native/probe_git_metadata.py'
s=importlib.util.spec_from_file_location('git_probe',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

class MetadataDenialTests(unittest.TestCase):
 def test_index_write_denials(self):
  for error in ('Read-only file system','Permission denied'):
   self.assertTrue(m.metadata_denied({'exitCode':128,'stderr':"fatal: Unable to create '/fixture/.git/worktrees/task/index.lock': "+error}))
 def test_unrelated_failures_rejected(self):
  for error in ('nothing to commit','Author identity unknown','git: command not found','Read-only file system'):
   self.assertFalse(m.metadata_denied({'exitCode':1,'stderr':error}))
 def test_success_cannot_be_denial(self):
  self.assertFalse(m.metadata_denied({'exitCode':0,'stderr':'index.lock: Permission denied'}))

 def test_fork_failure_is_not_sibling_denial(self):
  target=Path('/nonexistent-rras-fixture/outside.txt')
  self.assertFalse(m.sibling_denied({'exitCode':101,'stderr':'failed to fork sandboxed command: Resource temporarily unavailable'},target,True))
 def test_sibling_requires_read_control_and_target_error(self):
  target=Path('/nonexistent-rras-fixture/outside.txt')
  reply={'exitCode':2,'stderr':str(target)+': Read-only file system'}
  self.assertTrue(m.sibling_denied(reply,target,True))
  self.assertFalse(m.sibling_denied(reply,target,False))
