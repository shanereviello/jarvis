"""Synthetic-only fixture seeding and generated-key startup, never production."""
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'vendor'))
STATE=Path('/var/lib/rras-history-web-acceptance-projects-20261106')
WORK='wrk_'+'6'*32
DOC='doc_'+'7'*32


def load(directory,name):
    spec=importlib.util.spec_from_file_location('web_fixture_'+directory+'_'+name,ROOT/'engineering/tools'/directory/(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def seed():
    if os.getuid()!=61172:raise ValueError('fixed fixture owner required')
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
    projects=load('rras_history','projects').Projects(store)
    projects.migrate(projects.migration_plan()['expected_sha256'])
    project_id='prj_'+'8'*32
    selected={'kind':'repository','id':'fixture_library'}
    counter=0
    def project(operation,body):
        nonlocal counter
        counter+=1
        previous=None if operation=='project.create' else projects.read(selected,{'view':'project','project_id':project_id})['project']['head']
        return projects.submit(dict(contract='engineering-project.v1',operation=operation,
            client_event_key='synthetic-project-'+str(counter),expected_head=previous,scope=selected,project_id=project_id,
            source={'kind':'agent_reported','namespace':'host_fixture','id':None},occurred_at=None,body=body))
    metadata=dict(revision=1,name='Synthetic project workspace',overview='Synthetic grouping and design history',
        intended_outcome='Read immutable project views',in_scope='Fixture history',out_of_scope='Production',
        owner=None,change_summary='Initial synthetic project')
    project('project.create',metadata)
    baseline=project('baseline.record',dict(baseline_id='bas_'+'8'*32,version=1,previous_sha256=None,
        commit='a'*40,ref='main',label='Synthetic commit',reason='Fixture reference',source_reference=None,verified_at=None))['receipt']['effect']['baseline']
    for role in ('starting','current'):
        project('baseline.select',dict(role=role,version=1,baseline_sha256=baseline['baseline_sha256'],reason='Fixture selection'))
    saved=project('architecture.save',dict(document_id='doc_'+'8'*32,version=1,previous_sha256=None,
        title='Synthetic architecture',change_summary='Initial design',markdown='# Synthetic architecture\n\nOriginal design.\n',source_reference=None))['receipt']['effect']['architecture']
    project('architecture.designate',dict(version=1,markdown_sha256=saved['markdown_sha256'],reason='Fixture governing version'))
    project('membership.assign',dict(work_item_id=WORK,expected_assignment_sha256=None,
        expected_previous_project_head=None,architecture_version=1,reason='Fixture explicit assignment'))
    project('architecture.save',dict(document_id='doc_'+'8'*32,version=2,previous_sha256=saved['markdown_sha256'],
        title='Synthetic architecture',change_summary='Saved draft',markdown='# Synthetic architecture\n\nRevised design.\n',source_reference=None))
    project_id='prj_'+'9'*32
    selected={'kind':'non_git','id':'jarvis-non-git'}
    project('project.create',dict(metadata,name='Synthetic non-Git project'))
    project('architecture.save',dict(document_id='doc_'+'9'*32,version=1,previous_sha256=None,
        title='Non-Git architecture',change_summary='Initial draft',markdown='# Non-Git design\n',source_reference=None))
    print(json.dumps({'seeded':True,'records':2,'project_records':counter,'schema_version':2}))


def serve():
    if os.getuid()!=61173:raise ValueError('fixed fixture dashboard required')
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
