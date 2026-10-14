import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]/'tools/rras_native'
def load(name):
 s=importlib.util.spec_from_file_location(name,ROOT/(name+'.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
m=load('probe_integrated_runner');a=load('activity')

class CommitTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.repo=Path(self.tmp.name)
  def git(*args):subprocess.run(['git','-C',str(self.repo),*args],check=True,capture_output=True)
  self.git=git;git('init','-q');(self.repo/'calc.py').write_text('old\n');(self.repo/'AGENTS.md').write_text('preserve\n');git('add','.')
  git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','baseline')
 def test_commit_only_admitted_change(self):
  (self.repo/'calc.py').write_text('new\n');m.commit_validated_change(self.repo,None,a)
  self.assertFalse(a.git(self.repo,'status','--porcelain').strip())
 def test_unexpected_file_refused_without_staging(self):
  (self.repo/'calc.py').write_text('new\n');(self.repo/'AGENTS.md').write_text('changed\n')
  with self.assertRaises(ValueError):m.commit_validated_change(self.repo,None,a)
  self.assertFalse(a.git(self.repo,'diff','--cached').strip())
 def test_symlink_refused(self):
  (self.repo/'calc.py').unlink();(self.repo/'calc.py').symlink_to('AGENTS.md')
  with self.assertRaises(ValueError):m.commit_validated_change(self.repo,None,a)
