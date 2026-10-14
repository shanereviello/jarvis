import importlib.util,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
s=importlib.util.spec_from_file_location('context_cli',Path(__file__).resolve().parents[1]/'tools/rras_native/native_task_cli.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class TaskContextTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.home=self.root/'home';self.home.mkdir();self.context=self.root/'context.json'
  m.write_context(self.context,'t_fixture',1,self.home,self.home/'kanban.db',m.TRUSTED_PYTHON)
 def test_no_overwrite_and_mode(self):
  self.assertEqual(self.context.stat().st_mode & 0o777,0o400)
  with self.assertRaises(FileExistsError):m.write_context(self.context,'t_other',2,self.home,self.home/'kanban.db',m.TRUSTED_PYTHON)
  self.assertEqual(m.read_context(self.context)['task'],'t_fixture')
 def test_explicit_identity_without_inherited_credentials(self):
  with patch.dict(os.environ,{'OPENAI_API_KEY':'SECRET','HERMES_KANBAN_RUN_ID':'999'},clear=True),patch.object(m.subprocess,'run') as run:
   run.return_value.returncode=0;self.assertEqual(m.invoke(self.context,'complete','tests passed'),0)
   kwargs=run.call_args.kwargs;self.assertEqual(kwargs['env']['HERMES_KANBAN_RUN_ID'],'1');self.assertNotIn('OPENAI_API_KEY',kwargs['env']);self.assertIn('t_fixture',run.call_args.args[0])
 def test_symlink_writable_and_wrong_run_refused(self):
  link=self.root/'link';link.symlink_to(self.context)
  with self.assertRaises(OSError):m.read_context(link)
  self.context.chmod(0o600)
  with self.assertRaises(ValueError):m.read_context(self.context)
 def test_unadmitted_operation_refused(self):
  with self.assertRaises(ValueError):m.invoke(self.context,'dispatch')
