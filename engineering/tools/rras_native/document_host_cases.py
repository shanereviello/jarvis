"""Synthetic document cases shared with the actual workflow host fixture."""
import importlib.util
import uuid
from pathlib import Path


def local(name):
    s=importlib.util.spec_from_file_location('document_cases_'+name,Path(__file__).with_name(name+'.py'))
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


def initialize(operator,state,captured,config,work):
    a=local('activity');doc=local('document_approval');rid=captured['review_id']
    legacy=operator.approve(state,rid,config,approve_one_execution=True)
    engineering={'contract':'engineering-history.v1','operation':'work.create','client_event_key':'offline-document-work',
        'expected_head':None,'source':{'kind':'agent_reported','namespace':'offline-fixture','id':None},'occurred_at':None,
        'body':{'work_item_id':work['work_item_id'],'repository_id':work['repository_id'],'revision':1,
                'title':'Offline protected document acceptance','objective':work['objective'],
                'rationale':'Verify document custody without provider calls',
                'acceptance_criteria':[{'id':'AC1','description':'Document changes refuse before consumption'}],
                'allowed_paths':work['requested_paths'],'baseline':work['baseline']}}
    narrative={key:'unknown; offline fixture only' for key in doc.local('managed_review','rras_history').NARRATIVE}
    docid='doc_'+a.digest(str(state).encode())[:32]
    prepared=doc.prepare(state,rid,config,engineering,narrative,docid)
    view=doc.view(state,rid,config)
    if a.digest(view['markdown'].encode())!=prepared['markdown_sha256']:raise ValueError('exact document view differs')
    try:operator.approve(state,rid,config,approve_one_execution=True)
    except ValueError as error:
        if 'document-bound' not in str(error):raise
    else:raise ValueError('new legacy approval bypassed document attachment')
    for binding,markdown,flag in ((prepared['document_binding_sha256'],prepared['markdown_sha256'],False),
                                 ('a'*64,prepared['markdown_sha256'],True),
                                 (prepared['document_binding_sha256'],'b'*64,True)):
        try:doc.approve(state,rid,config,binding,markdown,approve_one_execution=flag)
        except ValueError:pass
        else:raise ValueError('incorrect document approval accepted')
    def grant():
        return doc.approve(state,rid,config,prepared['document_binding_sha256'],prepared['markdown_sha256'],approve_one_execution=True)
    first,second=grant(),grant()
    if first['schema_version']!=2 or second['schema_version']!=2:raise ValueError('v2 grant required')
    return {'legacy':legacy,'first':first,'second':second,'prepared':prepared}


def negative_launches(invoke,state,captured,config,bundle,jobs):
    """Only synthetic private copies are changed/restored; no real task state."""
    a=local('activity');rid=captured['review_id'];auth=bundle['second'];doc=local('document_approval')
    if list(Path(jobs).iterdir()):raise ValueError('negative cases require empty fixture jobs')
    def refused(authorization):
        try:invoke(authorization['authorization_id'])
        except (ValueError,OSError):pass
        else:raise ValueError('tampered document launch accepted')
        if (state/(authorization['authorization_id']+'.consumed.json')).exists():raise ValueError('negative case consumed grant')
        if list(Path(jobs).iterdir()):raise ValueError('negative case staged jobs')
    markdown=state/(rid+'.review.md');original=markdown.read_bytes()
    # Save immutable originals as additional private diagnostic evidence.
    a.absent(state/'original-review.md',original)
    markdown.write_bytes(original+b'\nSYNTHETIC TAMPER\n')
    refused(auth)
    markdown.write_bytes(original)
    renamed=state/'missing-review-retained.md';markdown.rename(renamed)
    refused(auth)
    renamed.rename(markdown)
    package=doc.marker(state,rid);raw=package.read_bytes();a.absent(state/'original-review-document.json',raw)
    changed=a.load(package);changed['package']['binding']['markdown_sha256']='e'*64
    package.write_bytes(a.encoded(changed))
    refused(auth)
    package.write_bytes(raw)
    for change in ({'markdown_sha256':'f'*64},{'schema_version':1},{'review_id':'d'*64}):
        bad=dict(auth,authorization_id=uuid.uuid4().hex,**change)
        a.absent(state/(bad['authorization_id']+'.approval.json'),a.encoded(bad));refused(bad)
    with local('approval').protocol_lock(state):
        try:doc.approve(state,rid,config,bundle['prepared']['document_binding_sha256'],bundle['prepared']['markdown_sha256'],approve_one_execution=True)
        except ValueError as error:
            if 'another approval' not in str(error):raise
        else:raise ValueError('concurrent approval lock bypassed')
    return ['changed_markdown_refused_unconsumed','missing_markdown_refused_unconsumed',
            'changed_package_refused_unconsumed','wrong_hash_protocol_capture_refused_unconsumed','approval_lock_exclusion']
