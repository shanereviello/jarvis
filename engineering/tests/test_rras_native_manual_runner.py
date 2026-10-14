import importlib.util,json,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]/'tools/rras_native'
s=importlib.util.spec_from_file_location('manual',ROOT/'manual_runner.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
a=m.local('activity')
class ManualRunnerTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.repo=self.root/'repo';self.repo.mkdir()
  self.git=lambda *args:subprocess.run(['git','-C',str(self.repo),*args],capture_output=True,check=True)
  self.git('init','-q');(self.repo/'value.py').write_text('value=0\n');(self.repo/'AGENTS.md').write_text('Original instructions\n');self.git('add','.');self.git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','baseline')
  self.r={'schema_version':1,'task_id':'TASK-general','repository_id':'fixture','objective':'Set value to one','allowed_paths':['value.py','new.py'],'validation_argv':['/usr/bin/python3','-B','-m','unittest'],'worker_timeout_seconds':30,'validation_timeout_seconds':10,'commit_policy':'leave_uncommitted'}
  self.file=self.root/'request.json';self.file.write_text(json.dumps(self.r));self.record={'baseline_commit':a.git(self.repo,'rev-parse','HEAD').decode().strip()}
 def test_request_refuses_unsafe_paths_and_implicit_commit(self):
  for key,value in [('allowed_paths',['../outside']),('allowed_paths',['AGENTS.md']),('allowed_paths',['.git/config']),('commit_policy','commit'),('validation_argv',['python','-m','unittest']),('worker_timeout_seconds',True)]:
   r=dict(self.r);r[key]=value;self.file.write_text(json.dumps(r))
   with self.assertRaises(ValueError):m.request(self.file)
 def test_exact_scope_tracks_new_files_and_refuses_extra(self):
  (self.repo/'new.py').write_text('new=1\n');self.assertEqual(m.scope(a,self.repo,self.record,self.r),['new.py'])
  (self.repo/'unexpected.py').write_text('outside=1\n')
  with self.assertRaises(ValueError):m.scope(a,self.repo,self.record,self.r)
 def test_symlink_refused(self):
  (self.repo/'value.py').unlink();(self.repo/'value.py').symlink_to('AGENTS.md')
  with self.assertRaises(ValueError):m.scope(a,self.repo,self.record,self.r)
 def test_instruction_overlay_restores_exact_originals(self):
  original,injected=m.install_instructions(self.repo,self.root,self.r,'/usr/bin/python3')
  self.assertIn(b'--context',injected['RRAS_TASK.md']);m.restore_instructions(self.repo,original,injected)
  self.assertEqual((self.repo/'AGENTS.md').read_text(),'Original instructions\n');self.assertFalse((self.repo/'RRAS_TASK.md').exists())
 def test_tampered_overlay_not_erased(self):
  original,injected=m.install_instructions(self.repo,self.root,self.r,'/usr/bin/python3');(self.repo/'RRAS_TASK.md').write_text('worker changed control\n')
  with self.assertRaises(ValueError):m.restore_instructions(self.repo,original,injected)
  self.assertEqual((self.repo/'RRAS_TASK.md').read_text(),'worker changed control\n');self.assertEqual((self.repo/'AGENTS.md').read_bytes(),injected['AGENTS.md'])
 def test_existing_state_preserved(self):
  work=self.root/'work';work.mkdir(mode=0o700);(work/'existing').write_text('preserve')
  with self.assertRaises(ValueError):m.run(None,None,None,None,None,None,work)
  self.assertEqual((work/'existing').read_text(),'preserve');self.assertFalse((work/'evidence.json').exists())


 def test_additional_artifact_is_hash_verified_in_export(self):
  registry=self.root/'registry.json';registry.write_text(json.dumps({'schema_version':1,'repositories':[{'repository_id':'fixture','path':str(self.repo),'enabled':True,'hermes_project':'fixture'}]}))
  state=self.root/'index';a.admit(state,registry,'TASK-general','fixture','Fixture');a.bind(state,'TASK-general','default','t_fixture','1')
  artifact=self.root/'new-files.json';artifact.write_text('{"notes.txt":"Zml4dHVyZQ=="}')
  exported=a.export(state,'TASK-general',self.repo,artifacts=[artifact]);folder=Path(exported['path']);manifest=a.verify_export(folder)
  self.assertEqual(manifest['additional_artifacts'],['additional-artifact-0.json'])
  (folder/'additional-artifact-0.json').write_text('tampered')
  with self.assertRaises(a.RecordError):a.verify_export(folder)
