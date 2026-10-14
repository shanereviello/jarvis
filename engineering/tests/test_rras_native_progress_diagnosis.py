import importlib.util
import json
from pathlib import Path
import unittest
s=importlib.util.spec_from_file_location('progress',Path(__file__).resolve().parents[1]/'tools/rras_native/diagnose_canary_progress.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

class ProgressTests(unittest.TestCase):
 def test_telemetry_distinct_from_rate_error(self):
  e=m.summarize('{"rate_limits":{}}')
  self.assertEqual(e['markers']['telemetry_field'],1)
  self.assertEqual(e['markers']['rate_message'],0)
 def test_raw_command_key_and_output_not_printed(self):
  text=json.dumps({'type':'event_msg','timestamp':'2026-10-12T18:44:00Z','payload':{'type':'exec_command_end','exit_code':1,'command':'PRIVATE-COMMAND','output':'SECRET-FIXTURE Permission denied'}})
  e=m.summarize(text)
  self.assertNotIn('SECRET-FIXTURE',str(e));self.assertNotIn('PRIVATE-COMMAND',str(e))
  self.assertEqual(e['exit_codes'],{'1':1});self.assertEqual(e['markers']['permission_failure'],1)
 def test_unknown_event_and_timestamp_never_exposed(self):
  e=m.summarize(json.dumps({'type':'PRIVATE-FIXTURE','timestamp':'SECRET','payload':{'type':'PRIVATE-FIXTURE'}}))
  self.assertFalse(e['events']);self.assertFalse(e['last_events'])
