import importlib.util,json,subprocess,tempfile,unittest,tomllib
from unittest.mock import patch
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
 def test_native_handoff_keeps_repository_instructions_untouched(self):
  config=self.root/'config.toml';config.write_text('sandbox_mode="workspace-write"\n[features]\napps=false\n')
  before=(self.repo/'AGENTS.md').read_bytes()
  expected=m.configure_instructions(self.root,self.r,'/usr/bin/python3',config)
  settings=tomllib.loads(config.read_text())
  self.assertIn('--context',settings['developer_instructions']);self.assertIn(self.r['objective'],settings['developer_instructions'])
  self.assertFalse(settings['features']['apps']);self.assertEqual((self.repo/'AGENTS.md').read_bytes(),before)
  self.assertFalse((self.repo/'RRAS_TASK.md').exists());m.verify_instructions(config,expected)
  self.assertEqual(m.scope(a,self.repo,self.record,self.r),[])
 def test_large_unicode_objective_not_truncated(self):
  config=self.root/'config.toml';config.write_text('approval_policy="on-request"\n')
  r=dict(self.r,objective='A'*10000+' end 🚀')
  m.configure_instructions(self.root,r,'/usr/bin/python3',config)
  self.assertIn(r['objective'],tomllib.loads(config.read_text())['developer_instructions'])
 def test_exact_failed_run_deletion_pattern_no_injected_files_to_remove(self):
  (self.repo/'AGENTS.md').unlink();self.git('add','AGENTS.md');self.git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','no controls baseline')
  self.record['baseline_commit']=a.git(self.repo,'rev-parse','HEAD').decode().strip()
  config=self.root/'config.toml';config.write_text('sandbox_mode="workspace-write"\n')
  expected=m.configure_instructions(self.root,self.r,'/usr/bin/python3',config)
  for name in ('AGENTS.md','RRAS_TASK.md'):(self.repo/name).unlink(missing_ok=True)
  m.verify_instructions(config,expected);self.assertEqual(m.scope(a,self.repo,self.record,self.r),[])
 def test_repository_control_deletion_or_alteration_still_fails_scope(self):
  for content in (None,'modified'):
   p=self.repo/'AGENTS.md'
   if content is None:p.unlink()
   else:p.write_text(content)
   with self.assertRaises(ValueError):m.scope(a,self.repo,self.record,self.r)
 def test_changed_session_configuration_is_retained_and_classified(self):
  config=self.root/'config.toml';config.write_text('sandbox_mode="workspace-write"\n')
  expected=m.configure_instructions(self.root,self.r,'/usr/bin/python3',config);config.write_text('altered')
  with self.assertRaises(m.HandoffError) as caught:m.verify_instructions(config,expected)
  self.assertEqual(caught.exception.code,'session_configuration_changed');self.assertEqual(config.read_text(),'altered')
 def test_existing_developer_instructions_refused_without_overwrite(self):
  config=self.root/'config.toml';original='developer_instructions="retain"\n';config.write_text(original)
  with self.assertRaises(m.HandoffError):m.configure_instructions(self.root,self.r,'/usr/bin/python3',config)
  self.assertEqual(config.read_text(),original)
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

 def test_preflight_diagnostic_does_not_leak_exception_payload(self):
  work=self.root/'work';work.mkdir(mode=0o700)
  with patch.object(m,'_run',side_effect=ValueError('sensitive exception content')):
   result=m.run(None,None,None,None,None,None,work)
  self.assertEqual(result['error_code'],'preflight_failed')
  self.assertFalse(result['worker_started']);self.assertNotIn('sensitive',json.dumps(result))
