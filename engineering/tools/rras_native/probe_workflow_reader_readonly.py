"""Model-free MCP2 probe for a synthetic fixture mounted read-only at /acceptance."""
import asyncio,errno,json,os,sys
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
async def run():
 root=Path('/acceptance');work=json.loads((root/'views/index.json').read_text())['pages'][0]['work_item_id']
 assert os.getuid()==1000
 try:(root/'views/write-must-fail').open('xb')
 except OSError as error:assert error.errno==errno.EROFS
 else:raise AssertionError('projection bind is writable')
 params=StdioServerParameters(command=sys.executable,args=['-I','-B',str(root/'engineering/tools/rras_native/workflow_read_stdio.py'),'--directory',str(root/'views')],env={'PATH':'/usr/bin:/bin','HOME':'/tmp'})
 async with stdio_client(params) as (read,write):
  async with ClientSession(read,write) as client:
   await client.initialize();listing=await client.list_tools()
   assert {t.name for t in listing.tools}=={'workflow_pages','workflow_history'}
   value=await client.call_tool('workflow_history',{'work_item_id':work});assert not value.model_dump(by_alias=True).get('isError')
   assert 'PRIVATE_FIXTURE_TEXT' not in json.dumps(value.model_dump(by_alias=True))
 return {'phase':'hermes_image_readonly_projection_verified','uid':os.getuid(),'api_calls':0,'read_only_bind_verified':True,'private_host_data_mounted':False,'network':'none','cases':['EROFS_projection_write','actual_stdio_readback','only_read_tools','private_fields_omitted']}
if __name__ == '__main__':
 print(json.dumps(asyncio.run(asyncio.wait_for(run(),timeout=40))))
