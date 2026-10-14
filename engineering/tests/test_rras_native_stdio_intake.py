"""Actual MCP stdio transport; no Hermes model or execution worker involved."""
import asyncio
import json
from pathlib import Path
import sys
import tempfile
import unittest

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = Path(__file__).resolve().parents[1]/'tools/rras_native/stdio_intake.py'

class StdioIntakeTests(unittest.TestCase):
    def test_actual_transport_proposals_only(self):
        async def exercise():
            with tempfile.TemporaryDirectory() as directory:
                root=Path(directory);policy=root/'policy.json'
                policy.write_text(json.dumps({'schema_version':1,'identities':{'hermes':['robot_ws']},'repositories':{
                    'robot_ws':{'enabled':True,'allowed_paths':['node.py'],
                    'validations':{'unit':['/usr/bin/python3','-m','unittest']},
                    'worker_timeout_seconds':300,'validation_timeout_seconds':60}}}))
                params=StdioServerParameters(command=sys.executable,args=['-I','-B',str(SERVER),'--policy',str(policy),'--state',str(root/'state')],env={'PATH':'/usr/bin:/bin'})
                async with stdio_client(params) as (read,write):
                    async with ClientSession(read,write) as client:
                        await client.initialize()
                        listing=await client.list_tools()
                        self.assertEqual({t.name for t in listing.tools},{'prepare_coding_task','coding_task_proposal'})
                        proposal={'task_id':'TASK-stdio','repository_id':'robot_ws','objective':'Fix velocity',
                                  'allowed_paths':['node.py'],'validation_id':'unit'}
                        result=await client.call_tool('prepare_coding_task',proposal)
                        self.assertFalse(result.model_dump(by_alias=True).get("isError",False))
                        receipt=result.model_dump(by_alias=True).get("structuredContent")
                        if receipt is None:receipt=json.loads(result.content[0].text)
                        same=await client.call_tool('prepare_coding_task',proposal)
                        second=same.model_dump(by_alias=True).get("structuredContent") or json.loads(same.content[0].text)
                        self.assertEqual(receipt['submission_id'],second['submission_id'])
                        readback=await client.call_tool('coding_task_proposal',{'submission_id':receipt['submission_id']})
                        data=readback.model_dump(by_alias=True).get("structuredContent") or json.loads(readback.content[0].text)
                        self.assertEqual(data['authenticated_identity'],'hermes')
                        self.assertFalse(data['execution_authorized']);self.assertFalse(data['publication_authorized'])
                        refused=await client.call_tool('prepare_coding_task',dict(proposal,repository_id='unapproved'))
                        self.assertTrue(refused.model_dump(by_alias=True).get("isError",False))
                        refused=await client.call_tool('prepare_coding_task',dict(proposal,allowed_paths=['outside.py']))
                        self.assertTrue(refused.model_dump(by_alias=True).get("isError",False))
                        self.assertEqual(len(list((root/'state').glob('*.json'))),1)
        asyncio.run(asyncio.wait_for(exercise(),timeout=30))

    def test_environment_is_scrubbed(self):
        # Run only in a child so the test process retains its environment.
        import subprocess
        code='''import importlib.util,os,sys
from pathlib import Path
p=Path(sys.argv[1]);s=importlib.util.spec_from_file_location('stdio',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
os.environ.update(OPENAI_API_KEY='harmless-fixture',GITHUB_TOKEN='harmless-fixture',RRAS_OPENAI_API_KEY='harmless-fixture')
m.server('/unused-policy','/unused-state')
assert set(os.environ)<= {'PATH','HOME','LANG','LC_ALL'}
'''
        subprocess.run([sys.executable,'-I','-B','-c',code,str(SERVER)],check=True,capture_output=True,timeout=15)

if __name__ == '__main__':
    unittest.main()
