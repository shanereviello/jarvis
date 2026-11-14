import base64,hashlib,importlib.util,tempfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]/'tools'
def load(area,name):
 spec=importlib.util.spec_from_file_location('fixture_'+name,root/area/(name+'.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
with tempfile.TemporaryDirectory() as temp:
 base=Path(temp);store_root=base/'private';store_root.mkdir(mode=0o700)
 store=load('rras_history','store').Store(store_root,create=True)
 projects=load('rras_history','projects').Projects(store);projects.migrate(projects.migration_plan()['expected_sha256'])
 scopes=load('rras_history','scopes').Scopes(store);scopes.migrate(scopes.migration_plan()['expected_sha256'])
 reporting=load('rras_history','reporting').Reporting(store);reporting.migrate(reporting.migration_plan()['expected_sha256'])
 evidence=load('rras_history','evidence').Evidence(store);evidence.migrate(evidence.migration_plan()['expected_sha256'])
 capture=load('rras_reporting','capture_intake');spool=capture.Spool(base/'spool',create=True)
 scope={'kind':'repository','id':'jarvis'};raw=b'X'*65536+b'Y'*65536+b'Z'*42
 staged=spool.stage(raw,scope=scope,context=None,session={'namespace':'codex','id':'synthetic'},collector='fixture',collector_version='1',source_sha256=hashlib.sha256(raw).hexdigest())
 def send(m):return evidence.upload(m['request']) if m['method']=='evidence_upload' else reporting.submit(m['request'])
 assert spool.flush(send)['failed']==0
 snap=projects.read(scope,{'view':'reporting'})['snapshot'];query={'artifact_id':staged['artifact_id'],'version':1,'snapshot':snap,'index':0,'count':3}
 got=evidence.read(scope,query);assert b''.join(base64.b64decode(x['data_base64']) for x in got['chunks'])==raw
 assert base64.b64decode(evidence.read(scope,{k:v for k,v in query.items() if k!='count'})['chunk']['data_base64'])==raw[:65536]
 for invalid in (dict(query,count=0),dict(query,count=9),dict(query,count=True),dict(query,index=1,count=3),dict(query,index=-1),dict(query,unexpected=True)):
  try:evidence.read(scope,invalid)
  except ValueError:pass
  else:raise AssertionError('invalid batch accepted')
 other=dict(scope,id='other')
 try:evidence.read(other,query)
 except ValueError:pass
 else:raise AssertionError('cross-scope signed boundary accepted')
 web=load('rras_history_web','history')
 reader=web.Reader(['jarvis'],lambda message:evidence.read(message['scope'],message['query']))
 web_query=dict(query,view='artifact');assert len(reader.workspace(scope,web_query)['chunks'])==3
 def tampered(message):
  answer=evidence.read(message['scope'],message['query']);answer['chunks'][1]['data_base64']=base64.b64encode(b'changed').decode();return answer
 try:web.Reader(['jarvis'],tampered).workspace(scope,web_query)
 except ValueError:pass
 else:raise AssertionError('tampered web chunk accepted')
 import asyncio,httpx
 appmodule=load('rras_history_web','app')
 class Access:
  def verify(self,headers):return {'email':'fixture@example.invalid'}
 app=appmodule.create_app(reader,Access())
 async def http_check():
  async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://fixture.invalid') as client:
   params={'scope_kind':'repository','scope_id':'jarvis','artifact_id':staged['artifact_id'],'version':1,'snapshot':__import__('json').dumps(snap),'index':0,'count':3}
   response=await client.get('/api/workspace/artifact',params=params);assert response.status_code==200 and len(response.json()['chunks'])==3
   params['count']=9;response=await client.get('/api/workspace/artifact',params=params);assert response.status_code==503
   response=await client.post('/api/workspace/artifact',params=params);assert response.status_code==405
 asyncio.run(asyncio.wait_for(http_check(),10))
 print('Actual isolated history store: batch bytes, legacy chunk, invalid bounds and cross-scope denial passed.')
