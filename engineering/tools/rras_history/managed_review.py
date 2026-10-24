"""Passive standard document bound to an exact supplied protected capture.

The caller must establish capture custody. Digests do not authenticate supplied
JSON. This constructor does not read root state or change the approval protocol.
"""
import importlib.util
from pathlib import Path
import re


def local(name, family='rras_history'):
    path=Path(__file__).parents[1]/family/(name+'.py')
    spec=importlib.util.spec_from_file_location('managed_review_'+name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


NARRATIVE={'approach','alternatives','dependencies','validation_mapping','risks',
           'assumptions','open_decisions','unknowns','non_goals','denied_paths'}


def literal(value):
    """JSON in an unbreakable code fence; caller text cannot close the core block."""
    text=local('contract').encoded(value).decode().rstrip('\n')
    fence='`'*max(3,1+max((len(run) for run in re.findall(r'`+',text)),default=0))
    return '\n\n'+fence+'json\n'+text+'\n'+fence+'\n'


def checked_review(review,review_id):
    c=local('contract');review=c.decode(c.encoded(review))
    if c.digest(c.encoded(review))!=review_id:raise ValueError('exact capture digest required')
    required={'schema_version','submission_id','policy_sha256','request','canonical_repository',
              'baseline_commit','baseline_ref','hermes_project','profile','profile_sha256',
              'codex_config','codex_config_sha256','runner_files','execution_authorized','publication_authorized'}
    if (not required<=set(review) or set(review)-required-{'review_branch','admission'} or
            type(review['schema_version']) is not int or review['schema_version']!=1 or
            review['execution_authorized'] is not False or review['publication_authorized'] is not False):
        raise ValueError('unapproved capture v1 required')
    local('task_contract','rras_native').validate_request(review['request'])
    for field in ('submission_id','policy_sha256','profile_sha256','codex_config_sha256'):
        local('approval','rras_native').exact_digest(review[field])
    if not re.fullmatch('[0-9a-f]{40}',review['baseline_commit']):raise ValueError('exact baseline required')
    if not isinstance(review['runner_files'],dict) or not review['runner_files']:raise ValueError('runner digests required')
    for name,sha in review['runner_files'].items():
        if not re.fullmatch(r'[a-z_]+\.py',name):raise ValueError('runner name required')
        local('approval','rras_native').exact_digest(sha)
    for field in ('canonical_repository','baseline_ref','hermes_project','profile','codex_config'):
        if not isinstance(review[field],str) or not review[field] or '\0' in review[field]:raise ValueError('capture reference required')
    if 'review_branch' in review and not re.fullmatch('codex/[A-Za-z0-9][A-Za-z0-9_-]{0,120}',review['review_branch']):
        raise ValueError('dedicated review branch required')
    return review


def build(review,review_id,work_request,narrative,document_id,*,document_version=1,supersedes=None):
    c=local('contract');docs=local('documents');review=checked_review(review,review_id)
    work_request=c.validate(work_request)
    if work_request['operation'] not in ('work.create','work.revise'):raise ValueError('explicit work revision required')
    work=work_request['body'];request=review['request']
    if (work['repository_id']!=request['repository_id'] or work['allowed_paths']!=request['allowed_paths'] or
            work['baseline']!={'ref':review['baseline_ref'],'commit':review['baseline_commit']}):
        raise ValueError('exact repository, ordered scope and baseline binding required')
    if not isinstance(narrative,dict) or set(narrative)!=NARRATIVE:raise ValueError('exact curated narrative field set required')
    for value in narrative.values():
        if not isinstance(value,str) or not value.strip() or len(value.encode())>8192 or '\0' in value:
            raise ValueError('bounded explicit narrative or unknown required')
    template=(docs.TEMPLATES/'review.md').read_text()
    metadata={'work_item_id','work_revision','document_id','document_version','repository_id','created_at_or_unknown'}
    fields={key:'unknown' for key in set(re.findall(r'\{\{([a-z][a-z0-9_]*)\}\}',template))-metadata}
    fields.update({key:'Curated proposal (not an observed result):'+literal(value) for key,value in narrative.items()})
    fields.update(title=work['title'],problem=literal(work['objective']),rationale_and_source=literal(work['rationale']),
        request_source='Supplied capture and separately curated engineering revision; caller must establish protected custody.',
        expected_behavior=literal(request['objective']),acceptance_criteria=literal(work['acceptance_criteria']),
        interactive_or_managed_context='Managed proposal; no execution authorized by this document.',
        baseline=literal(work['baseline']),starting_state='Capture required a clean baseline; not re-observed by this renderer.',
        registration_status='Capture-time policy/admission references appear in the exact core below; current admission is not rechecked.',
        allowed_paths=literal(request['allowed_paths']),constraints='Exact captured core below; narrative cannot override it.',
        revision_relationship=literal({'revision':work['revision'],'previous_head':work_request['expected_head']}),
        recipe=literal(request['validation_argv']),
        validation_limits=literal({'timeout_seconds':request['validation_timeout_seconds'],'identity':'not established by this renderer'}),
        validation_limits_of_inference='No validation executed. Recipe completion alone does not establish task success.',
        interactive_recording_or_managed_execution='Passive review preparation for a managed capture.',
        capture_operation_id=literal({'submission_id':review['submission_id'],'task_id':request['task_id']}),
        protected_session_refs=literal({key:review[key] for key in ('profile_sha256','codex_config_sha256','runner_files')}),
        worker_limits=literal({'timeout_seconds':request['worker_timeout_seconds'],'commit_policy':request['commit_policy']}),
        spending_controls='No monetary ceiling established here; no paid run authorized or performed.',
        exact_action_or_recording_only='Review only. This companion is not an execution grant.',
        merge_deployment_and_further_paid_runs='Separate explicit decisions remain required.',
        claim_or_field_to_source_reference_table='Exact supplied capture core (private, not independently authenticated):'+literal(review))
    head=c.digest(c.encoded(work))
    document={'contract':'engineering-history.v1','operation':'document.render',
        'client_event_key':'managed-review-'+review_id+'-'+document_id,
        'expected_head':head,'source':{'kind':'imported','namespace':'managed-review','id':review_id},'occurred_at':None,
        'body':{'work_item_id':work['work_item_id'],'work_revision_sha256':head,'document_id':document_id,
                'document_version':document_version,'document_type':'review','supersedes_document_sha256':supersedes,
                'fields':fields,'references':[]}}
    document=c.validate(document);raw,manifest=docs.render(document,work)
    binding={'contract':'engineering-managed-review-binding.v1','review_id':review_id,
        'task_id':request['task_id'],'work_item_id':work['work_item_id'],'work_revision_sha256':head,
        'document_request_sha256':c.digest(c.encoded(document)),
        'document_manifest_sha256':c.digest(c.encoded(manifest)),'markdown_sha256':c.digest(raw),
        'binding_renderer_sha256':c.digest(Path(__file__).read_bytes()),
        'authority_granted':False,'approval_protocol':'existing_v1_unchanged'}
    return {'document_request':document,'manifest':manifest,'markdown':raw.decode(),'binding':binding}


def verify(package,review,review_id,work_request,narrative):
    body=package['document_request']['body']
    expected=build(review,review_id,work_request,narrative,body['document_id'],
                   document_version=body['document_version'],supersedes=body['supersedes_document_sha256'])
    if package!=expected:raise ValueError('exact review document package changed; rebuild and review')
    return {'verified':True,'binding_sha256':local('contract').digest(local('contract').encoded(expected['binding'])),
            'authority_granted':False,'execution_authorized':False}
