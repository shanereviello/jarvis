import importlib.util,json,unittest
from pathlib import Path
s=importlib.util.spec_from_file_location('completion',Path(__file__).resolve().parents[1]/'tools/rras_native/diagnose_native_completion.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class CompletionTests(unittest.TestCase):
 def test_only_classification_retained(self):
  records=[{'payload':{'type':'function_call','call_id':'PRIVATE-ID','arguments':json.dumps({'cmd':'python -m hermes_cli.main kanban complete "$HERMES_KANBAN_TASK" --result SECRET'})}}, {'payload':{'type':'function_call_output','call_id':'PRIVATE-ID','output':'SECRET No module named hermes_cli\nProcess exited with code 1'}}]
  result=m.summarize('\n'.join(map(json.dumps,records)))
  self.assertEqual(result[0]['operation'],'complete');self.assertTrue(result[0]['missing_module']);self.assertEqual(result[0]['exit_codes'],[1])
  self.assertNotIn('SECRET',str(result));self.assertNotIn('PRIVATE-ID',str(result))
 def test_absent_command_and_malformed_record(self):
  self.assertEqual(m.summarize('invalid\n'+json.dumps({'payload':{'type':'function_call','call_id':'x','arguments':'bad'}})),[])
 def test_unrelated_tool_output_not_adopted(self):
  records=[{'payload':{'type':'function_call','call_id':'a','arguments':json.dumps({'cmd':'hermes kanban show task'})}}, {'payload':{'type':'function_call_output','call_id':'b','output':'Process exited with code 0'}}]
  self.assertFalse(m.summarize('\n'.join(map(json.dumps,records)))[0]['result_observed'])

 def test_failure_categories_do_not_expose_details(self):
  records=[{'payload':{'type':'function_call','call_id':'a','arguments':json.dumps({'cmd':'hermes kanban show task'})}}, {'payload':{'type':'function_call_output','call_id':'a','output':'OperationalError: unable to open database file SECRET'}}]
  result=m.summarize('\n'.join(map(json.dumps,records)))[0]
  self.assertTrue(result['database_open_failed']);self.assertEqual(result['exceptions'],['OperationalError']);self.assertNotIn('SECRET',str(result))

 def test_shell_guard_classified_without_command_exposure(self):
  records=[{'payload':{'type':'function_call','call_id':'a','arguments':json.dumps({'cmd':'test -n "$HERMES_KANBAN_TASK" && python -m hermes_cli.main kanban show "$HERMES_KANBAN_TASK" || exit 1','login':False})}}, {'payload':{'type':'function_call_output','call_id':'a','output':'Process exited with code 1\nOutput:\n'}}]
  result=m.summarize('\n'.join(map(json.dumps,records)))[0]
  self.assertTrue(result['presence_guard']);self.assertTrue(result['explicit_exit_one']);self.assertTrue(result['output_body_empty']);self.assertTrue(result['requested_nonlogin_shell'])
