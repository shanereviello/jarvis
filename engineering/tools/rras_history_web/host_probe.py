"""Synthetic-only fixture seeding and generated-key startup, never production."""
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'vendor'))
STATE=Path('/var/lib/rras-history-web-acceptance-attempt02-20261104')
WORK='wrk_'+'6'*32
DOC='doc_'+'7'*32


def load(directory,name):
    spec=importlib.util.spec_from_file_location('web_fixture_'+directory+'_'+name,ROOT/'engineering/tools'/directory/(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def seed():
    if os.getuid()!=61162:raise ValueError('fixed fixture owner required')
    store=load('rras_history','store').Store(STATE/'history',create=True)
    def request(operation,key,head,body):return dict(contract='engineering-history.v1',operation=operation,client_event_key=key,
        expected_head=head,source={'kind':'agent_reported','namespace':'host_fixture','id':None},occurred_at=None,body=body)
    work=dict(work_item_id=WORK,revision=1,repository_id='fixture_library',title='Synthetic dashboard host acceptance',
        objective='Read exact synthetic work and documents',rationale='Prove a read-only boundary',
        acceptance_criteria=[{'id':'AC1','description':'Do not infer task success'}],allowed_paths=['docs/example.md'],baseline=None)
    head=store.submit(request('work.create','work',None,work))['receipt']['work_revision_sha256']
    template=(ROOT/'engineering/docs/engineering-history-phase1/templates/review.md').read_text()
    injected={'work_item_id','work_revision','document_id','document_version','repository_id','created_at_or_unknown'}
    fields={name:'synthetic fixture' for name in set(re.findall(r'\{\{([a-z][a-z0-9_]*)\}\}',template))-injected}
    fields['title']='Exact synthetic review'
    body=dict(work_item_id=WORK,work_revision_sha256=head,document_id=DOC,document_version=1,document_type='review',
        supersedes_document_sha256=None,fields=fields,references=[])
    store.submit(request('document.render','document',head,body))
    print(json.dumps({'seeded':True,'records':2}))


def serve():
    if os.getuid()!=61163:raise ValueError('fixed fixture dashboard required')
    entry=load('rras_history_web','entry');auth=entry.local('access')
    public=auth.strict_json((STATE/'public-keys.json').read_bytes());original=auth.Keys
    def keys(config):
        if config.issuer!='https://fixture.cloudflareaccess.com':raise ValueError('fixture issuer only')
        return original(config,loader=lambda:public)
    auth.Keys=keys
    # Only JWKS retrieval is synthetic. Actual entry, origin JWT verification,
    # identity/config checks, HTTP server and authenticated Unix reads run here.
    entry.main(['--config',str(STATE/'config.json')])


if __name__=='__main__':
    if sys.argv[1:] == ['seed']:seed()
    elif sys.argv[1:] == ['serve']:serve()
    else:raise ValueError('fixed fixture role required')
