"""Protected immutable review-document custody and opt-in v2 one-use approval.

No service launch, history import, provider call or public document publication.
"""
import importlib.util
import os
from pathlib import Path
import stat
import uuid


def local(name,family='rras_native'):
    spec=importlib.util.spec_from_file_location('document_approval_'+name,Path(__file__).parents[1]/family/(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def dependencies():
    base=Path(__file__).parents[2]
    return [Path(__file__),Path(__file__).with_name('publication_custody.py'),*(base/'tools/rras_history'/name for name in
            ('managed_review.py','documents.py','contract.py')),
            base/'contracts/engineering-history-v1.schema.json',
            base/'docs/engineering-history-phase1/templates/review.md']


def private_bytes(path):
    path=Path(path);info=path.stat()
    if info.st_uid!=0 or stat.S_IMODE(info.st_mode)!=0o600 or info.st_nlink!=1:
        raise ValueError('root-private single-link document record required')
    return local('publication_custody').root_bytes(path,1024*1024)


def private_read(path):
    return local('contract','rras_history').decode(private_bytes(path),max_bytes=1024*1024)


def read_proposal(path):
    """Read selected private JSON as data, refusing FIFOs/devices and symlinks."""
    path=Path(path)
    if not path.is_absolute() or path.resolve(strict=True)!=path:raise ValueError('canonical proposal path required')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        info=os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or stat.S_IMODE(info.st_mode)!=0o600 or
                info.st_size>128*1024):raise ValueError('bounded private regular proposal required')
        with os.fdopen(os.dup(fd),'rb') as stream:raw=stream.read(128*1024+1)
        return local('contract','rras_history').decode(raw)
    finally:os.close(fd)


def capture_record(state,review_id,config):
    operator=local('operator_control');state=operator.require_operator(state)
    for path in dependencies():operator.trusted(path)
    local('approval').exact_digest(review_id)
    review=private_read(state/(review_id+'.review.json'))
    a=local('activity')
    if a.digest(a.encoded(review))!=review_id:raise ValueError('protected capture changed')
    operator.validate_review(review,config)
    return state,review


def marker(state,review_id):
    local('approval').exact_digest(review_id)
    return Path(state)/(review_id+'.review-document.json')


def prepare(state,review_id,config,work_request,narrative,document_id,*,document_version=1,supersedes=None):
    state,review=capture_record(state,review_id,config)
    # Explicitly preserve the engineering identity already admitted operationally.
    if work_request['body']['work_item_id']!=review['admission']['work_item']['work_item_id']:
        raise ValueError('admitted engineering work identity required')
    builder=local('managed_review','rras_history')
    package=builder.build(review,review_id,work_request,narrative,document_id,
                          document_version=document_version,supersedes=supersedes)
    value={'contract':'protected-engineering-review.v1','review_id':review_id,
           'configuration':str(config),'work_request':work_request,'narrative':narrative,'package':package}
    a=local('activity');raw=a.encoded(value)
    if len(raw)>1024*1024:raise ValueError('protected document package exceeds bound')
    with local('approval').protocol_lock(state):
        a.absent(state/(review_id+'.review.md'),package['markdown'].encode())
        a.absent(marker(state,review_id),raw)
    return dict(summary(package),markdown_file=str(state/(review_id+'.review.md')))


def load(state,review_id):
    state=local('operator_control').require_operator(state)
    value=private_read(marker(state,review_id))
    if (set(value)!={'contract','review_id','configuration','work_request','narrative','package'} or
            value['contract']!='protected-engineering-review.v1' or value['review_id']!=review_id):
        raise ValueError('protected document identity differs')
    _,review=capture_record(state,review_id,value['configuration'])
    if value['work_request']['body']['work_item_id']!=review['admission']['work_item']['work_item_id']:
        raise ValueError('admitted engineering work identity required')
    local('managed_review','rras_history').verify(value['package'],review,review_id,value['work_request'],value['narrative'])
    if private_bytes(state/(review_id+'.review.md'))!=value['package']['markdown'].encode():
        raise ValueError('protected Markdown bytes changed')
    return value,review


def summary(package):
    a=local('activity');binding=package['binding']
    return {'review_id':binding['review_id'],'document_binding_sha256':a.digest(a.encoded(binding)),
            'document_manifest_sha256':binding['document_manifest_sha256'],'markdown_sha256':binding['markdown_sha256'],
            'execution_authorized':False,'publication_authorized':False}


def view(state,review_id,config):
    value,_=load(state,review_id)
    if str(config)!=value['configuration']:raise ValueError('different live configuration path')
    return dict(summary(value['package']),markdown=value['package']['markdown'],manifest=value['package']['manifest'],
                markdown_file=str(Path(state)/(review_id+'.review.md')))


def approve(state,review_id,config,binding_sha256,markdown_sha256,*,approve_one_execution=False):
    if approve_one_execution is not True:raise ValueError('explicit one-execution approval required')
    state=local('operator_control').require_operator(state)
    with local('approval').protocol_lock(state):
        value,review=load(state,review_id);expected=summary(value['package'])
        if str(config)!=value['configuration']:raise ValueError('different live configuration path')
        if binding_sha256!=expected['document_binding_sha256'] or markdown_sha256!=expected['markdown_sha256']:
            raise ValueError('exact reviewed binding and Markdown digests required')
        auth={'schema_version':2,'authorization_id':uuid.uuid4().hex,'review_id':review_id,
              'execution_authorized':True,'publication_authorized':False,'authorized_os_uid':os.getuid(),
              **{key:expected[key] for key in ('document_binding_sha256','document_manifest_sha256','markdown_sha256')}}
        local('activity').absent(state/(auth['authorization_id']+'.approval.json'),local('activity').encoded(auth))
    local('managed_events').record(review,review_id,'approved',auth['authorization_id'])
    return auth


def verify_authorization(state,auth):
    fields={'schema_version','authorization_id','review_id','execution_authorized','publication_authorized','authorized_os_uid',
            'document_binding_sha256','document_manifest_sha256','markdown_sha256'}
    if (set(auth)!=fields or type(auth['schema_version']) is not int or auth['schema_version']!=2 or
            type(auth['authorized_os_uid']) is not int or auth['authorized_os_uid']!=0 or auth['execution_authorized'] is not True or auth['publication_authorized'] is not False):
        raise ValueError('document-bound v2 authorization required')
    local('operator_control').authorization(auth['authorization_id'])
    value,_=load(state,auth['review_id']);expected=summary(value['package'])
    if any(auth[key]!=expected[key] for key in ('document_binding_sha256','document_manifest_sha256','markdown_sha256')):
        raise ValueError('approved document binding changed')
    return value
