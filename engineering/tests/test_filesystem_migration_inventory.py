import importlib.util,json,tempfile,unittest
from pathlib import Path
s=importlib.util.spec_from_file_location('inventory',Path(__file__).resolve().parents[1]/'tools/migration/inspect_filesystem.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class InventoryTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
 def test_only_path_counts_emitted(self):
  (self.root/'compose.yaml').write_text('password: SECRET-FIXTURE\npath: /srv/hermes-dev/jarvis\n')
  r=m.references([self.root]);self.assertEqual(r['references'][0]['path_reference_counts'],{'/srv/hermes-dev':1});self.assertNotIn('SECRET-FIXTURE',json.dumps(r));self.assertNotIn('password:',json.dumps(r))
 def test_secret_and_auth_files_excluded(self):
  for name in ('.env','auth.json','api_token','password.txt'):(self.root/name).write_text('/srv/hermes-dev SECRET')
  secret=self.root/'secrets';secret.mkdir();(secret/'config.yaml').write_text('/srv/hermes-dev SECRET')
  self.assertEqual(m.references([self.root])['files_examined'],0)
 def test_symlink_not_followed(self):
  outside=self.root/'real.conf';outside.write_text('/srv/jarvis-codex');link=self.root/'link.conf';link.symlink_to(outside)
  self.assertEqual(m.references([link])['files_examined'],0)
 def test_limit_fails_closed(self):
  (self.root/'a.sh').write_text('/srv/jarvis-activity')
  with self.assertRaises(ValueError):m.references([self.root],limit=0)

 def test_container_environment_and_commands_never_emitted(self):
  from unittest.mock import patch
  c={'Name':'/fixture','State':{'Status':'running'},'Image':'sha256:fixture','Config':{'Env':['TOKEN=SECRET-FIXTURE'],'Cmd':['SECRET-COMMAND'],'Labels':{}},'Mounts':[],'NetworkSettings':{'Networks':{},'Ports':{}}}
  with patch.object(m.subprocess,'check_output',side_effect=[b'fixture\n',json.dumps([c]).encode()]):r=m.containers()
  self.assertNotIn('SECRET',json.dumps(r));self.assertEqual(r[0]['name'],'/fixture')
