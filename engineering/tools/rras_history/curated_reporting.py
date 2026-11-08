"""Reusable selected-project publication profile for structured reporting only.

No private transcript bytes, source fallback, worker launcher or approval editor.
Profile approval is a trusted local installation decision, not human identity.
"""
import copy
from datetime import datetime,timezone
import importlib.util
import os
from pathlib import Path
import re
from jsonschema import Draft202012Validator,FormatChecker,ValidationError

LIMIT=2*1024*1024
FIELDS={
    'mapping.record':('kind','plan_id','linear','reason'),
    'attempt.record':('attempt_id','phase','actor','coordinator','baseline_commit','result','references'),
    'checkpoint.report':('report_id','attempt_id','observations','alternatives_and_reasons','changes','validation','open_questions','next_step','references'),
    'handoff.record':('handoff_id','sender','recipient','state','issue_id','requested_action','result','references'),
    'decision.observe':('decision_id','kind','state','attributed_author','attribution','source_reference','decision_text'),
    'artifact.record':('artifact_id','version','content_sha256','completeness','gaps','redaction_profile'),
    'source.observe':('status','source_observed_at','gaps','detail')}


def local(name):
    spec=importlib.util.spec_from_file_location('curated_reporting_'+name,Path(__file__).with_name(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def validate_profile(value):
    c=local('contract');value=c.decode(c.encoded(value),max_bytes=65536)
    if (type(value) is not dict or set(value)!={'contract','profile_id','version','projects','fields','authorization_reference'} or
            value['contract']!='engineering-reporting-publication-profile.v1' or
            type(value['profile_id']) is not str or not re.fullmatch('prf_[0-9a-f]{32}',value['profile_id']) or
            type(value['version']) is not int or not 1<=value['version']<=1000000 or
            type(value['projects']) is not list or not 1<=len(value['projects'])<=32 or
            type(value['fields']) is not dict or not value['fields'] or set(value['fields'])-set(FIELDS)):
        raise ValueError('exact bounded publication profile required')
    local('curated_preview').text(value['authorization_reference'],2048)
    seen=set()
    for project in value['projects']:
        if (type(project) is not dict or set(project)!={'project_id','repository_id'} or
                type(project['project_id']) is not str or not re.fullmatch('prj_[0-9a-f]{32}',project['project_id']) or
                type(project['repository_id']) is not str or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,95}',project['repository_id']) or
                project['project_id'] in seen):raise ValueError('explicit unique selected repository projects required')
        seen.add(project['project_id'])
    for operation,fields in value['fields'].items():
        if (type(fields) is not list or not fields or len(fields)!=len(set(fields)) or
                any(type(x) is not str or x not in FIELDS[operation] for x in fields)):
            raise ValueError('only approved structured fields may be published')
    return value


def projection(value,operation,fields):
    rc=local('reporting_contract');body=rc.DEFS[rc.OPERATIONS[operation]]
    schema=rc.obj(**{k:body['properties'][k] for k in fields});schema['$defs']=rc.DEFS
    schema_value(schema,value)


def schema_value(schema,value):
    try:Draft202012Validator(schema,format_checker=FormatChecker()).validate(value)
    except ValidationError:raise ValueError('typed curated projection differs') from None


def build(rows,profile,profile_sha256):
    profile=validate_profile(profile);c=local('contract');rc=local('reporting_contract')
    if c.digest(c.encoded(profile))!=profile_sha256:raise ValueError('exact installed profile digest required')
    if type(rows) is not list or len(rows)>10000:raise ValueError('bounded explicit reporting snapshot rows required')
    selected={p['project_id']:p['repository_id'] for p in profile['projects']};entries=[];seen=set()
    for row in rows:
        if type(row) is not dict or set(row)-{'submission','receipt','effective_context'} or not {'submission','receipt'}<=set(row):
            raise ValueError('explicit reporting source and receipt required')
        try:request=rc.validate(row['submission'])
        except ValidationError:raise ValueError('typed reporting source differs') from None
        receipt=row['receipt'];sha=c.digest(c.encoded(request))
        if (type(receipt) is not dict or receipt.get('request_sha256')!=sha or receipt.get('scope')!=request['scope'] or
                receipt.get('context')!=request['context'] or receipt.get('visibility')!='operator_private' or
                receipt.get('authority_granted') is not False or type(receipt.get('receipt_id')) is not str or
                not re.fullmatch('rcp_[0-9a-f]{32}',receipt['receipt_id'])):raise ValueError('exact reporting source receipt differs')
        recorded=receipt.get('recorded_at')
        if type(recorded) is not str or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?Z',recorded):
            raise ValueError('exact source recording time required')
        datetime.fromisoformat(recorded.replace('Z','+00:00'))
        if sha in seen:raise ValueError('duplicate source snapshot row')
        seen.add(sha);context=request['context'];operation=request['operation']
        if (operation not in profile['fields'] or context is None or context['project_id'] not in selected or
                request['scope']!=dict(kind='repository',id=selected[context['project_id']])):continue
        # Artifact association corrections are not silently folded into an
        # unrelated publication. Only the original explicit context is eligible.
        details={k:copy.deepcopy(request['body'][k]) for k in profile['fields'][operation]}
        details,_=local('redaction').redact_object(details)
        projection(details,operation,profile['fields'][operation])
        entry=dict(repository_id=request['scope']['id'],context=context,details=details,
            source_operation=operation,source_provenance=request['source']['kind'],source_request_sha256=sha,
            source_receipt_id=receipt['receipt_id'],source_recorded_at=recorded,source_occurred_at=request['occurred_at'],
            profile_sha256=profile_sha256,curation_provenance='installed_profile',source_authenticated=False,
            human_authenticated=False,release_status='not_inferred',redaction_profile='engineering-redaction-v1')
        entry['entry_id']='cur_'+c.digest(c.encoded(entry));entries.append(entry)
    entries.sort(key=lambda x:(x['source_recorded_at'],x['source_request_sha256']),reverse=True)
    preview=dict(contract='engineering-curated-reporting-preview.v1',audience='jarvis_candidate',visibility='operator_private',
        publication_authorized=False,authority_granted=False,source_freshness='not_polled',profile=profile,profile_sha256=profile_sha256,
        coverage=dict(eligible_count=len(entries),returned_count=min(len(entries),100),limit=100),entries=entries[:100])
    validate_preview(preview)
    return preview


def validate_preview(value):
    c=local('contract');value=c.decode(c.encoded(value),max_bytes=LIMIT)
    if (type(value) is not dict or set(value)!={'contract','audience','visibility','publication_authorized','authority_granted',
            'source_freshness','profile','profile_sha256','coverage','entries'} or
            value['contract']!='engineering-curated-reporting-preview.v1' or value['audience']!='jarvis_candidate' or
            value['visibility']!='operator_private' or value['publication_authorized'] is not False or
            value['authority_granted'] is not False or value['source_freshness']!='not_polled' or
            type(value['entries']) is not list or len(value['entries'])>100):raise ValueError('bounded private reporting preview required')
    profile=validate_profile(value['profile']);sha=c.digest(c.encoded(profile));selected={p['project_id']:p['repository_id'] for p in profile['projects']}
    if value['profile_sha256']!=sha:raise ValueError('profile digest differs')
    coverage=value['coverage']
    if (type(coverage) is not dict or set(coverage)!={'eligible_count','returned_count','limit'} or coverage['limit']!=100 or
            type(coverage['eligible_count']) is not int or not len(value['entries'])<=coverage['eligible_count']<=10000 or
            type(coverage['returned_count']) is not int or coverage['returned_count']!=len(value['entries'])):
        raise ValueError('explicit bounded profile coverage required')
    fields={'entry_id','repository_id','context','details','source_operation','source_provenance','source_request_sha256',
        'source_receipt_id','source_recorded_at','source_occurred_at','profile_sha256','curation_provenance',
        'source_authenticated','human_authenticated','release_status','redaction_profile'}
    seen=set();rc=local('reporting_contract')
    for entry in value['entries']:
        if type(entry) is not dict or set(entry)!=fields:raise ValueError('exact reporting publication entry required')
        body={k:v for k,v in entry.items() if k!='entry_id'}
        if entry['entry_id']!='cur_'+c.digest(c.encoded(body)) or entry['entry_id'] in seen:raise ValueError('entry digest differs')
        seen.add(entry['entry_id']);context=entry['context']
        schema_value(dict(rc.DEFS['context'],**{'$defs':rc.DEFS}),context)
        if (selected.get(context['project_id'])!=entry['repository_id'] or entry['profile_sha256']!=sha or
                entry['source_operation'] not in profile['fields'] or entry['curation_provenance']!='installed_profile' or
                entry['source_authenticated'] is not False or entry['human_authenticated'] is not False or
                entry['redaction_profile']!='engineering-redaction-v1' or
                entry['release_status']!='not_inferred' or entry['source_provenance'] not in ('agent_reported','human_reported','imported')):
            raise ValueError('reporting entry exceeds selected profile or implies authority')
        projection(entry['details'],entry['source_operation'],profile['fields'][entry['source_operation']])
        for k,pattern in [('source_request_sha256','[0-9a-f]{64}'),('source_receipt_id','rcp_[0-9a-f]{32}')]:
            if type(entry[k]) is not str or not re.fullmatch(pattern,entry[k]):raise ValueError('exact source reference required')
        for k in ('source_recorded_at','source_occurred_at'):
            if k=='source_occurred_at' and entry[k] is None:continue
            if type(entry[k]) is not str or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?Z',entry[k]):raise ValueError('exact source time required')
            datetime.fromisoformat(entry[k].replace('Z','+00:00'))
    return value


def search(preview,reviewed_sha256,repository_id,query,*,offset=0,limit=20):
    c=local('contract');preview=validate_preview(preview)
    if c.digest(c.encoded(preview))!=reviewed_sha256:raise ValueError('exact reporting preview digest required')
    if (type(repository_id) is not str or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,95}',repository_id) or
            type(query) is not str or len(query.encode())>256 or type(offset) is not int or offset<0 or
            type(limit) is not int or not 1<=limit<=50):raise ValueError('bounded exact curated query required')
    terms=query.casefold().split()
    entries=[x for x in preview['entries'] if x['repository_id']==repository_id and all(term in
        c.encoded(dict(context=x['context'],details=x['details'],operation=x['source_operation'])).decode().casefold() for term in terms)]
    page=entries[offset:offset+limit]
    return dict(entries=page,next_offset=offset+len(page),has_more=offset+len(page)<len(entries),preview_sha256=reviewed_sha256,
        publication_authorized=False,authority_granted=False,source_freshness='not_polled',coverage=preview['coverage'])


def publish_profile(root,rows,profile,profile_sha256,expected_head,*,approve_profile=False):
    if approve_profile is not True:raise ValueError('explicit installed profile approval required')
    c=local('contract');catalog=local('curated_publication');preview=build(rows,profile,profile_sha256)
    root,config=catalog.configuration(root);chain=catalog.chain(root,config);current=chain[0][0] if chain else None
    if current!=expected_head:raise ValueError('stale publication generation')
    withdrawn={entry for _,value in chain for entry in value['request']['withdrawn_ids']}
    preview['entries']=[x for x in preview['entries'] if x['entry_id'] not in withdrawn]
    preview['coverage']['returned_count']=len(preview['entries']);sha=c.digest(c.encoded(preview))
    if chain and c.encoded(chain[0][1]['preview'])==c.encoded(preview):
        return dict(chain[0][1]['receipt'],generation_sha256=current,replayed=True)
    key='profile-'+c.digest(c.encoded(dict(profile=profile_sha256,preview=sha,head=expected_head)))
    return catalog.publish(root,preview,sha,expected_head,key,approve_publication=True)


def install_profile(root,profile,reviewed_sha256,*,approve_profile=False):
    """Retain one immutable owner-approved profile; never activate a worker."""
    if approve_profile is not True:raise ValueError('explicit installed profile approval required')
    c=local('contract');d=local('link_delivery');profile=validate_profile(profile)
    if c.digest(c.encoded(profile))!=reviewed_sha256:raise ValueError('exact profile approval bytes required')
    root,config=local('curated_publication').configuration(root)
    if any(p['repository_id'] not in config['repositories'] for p in profile['projects']):raise ValueError('profile outside repository policy')
    folder=root/'profiles';folder.mkdir(mode=0o700,exist_ok=True);d.guard(folder)
    path=folder/(reviewed_sha256+'.json')
    if path.exists() or path.is_symlink():return installed_profile(root,reviewed_sha256)['receipt']
    receipt=dict(contract='engineering-curated-profile-receipt.v1',profile_sha256=reviewed_sha256,
        owner_uid=os.getuid(),recorded_at=datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),
        profile_approval_recorded=True,human_authenticated=False,authority_granted=False)
    d.write(path,dict(profile=profile,receipt=receipt));local('curated_publication').sync(folder)
    return receipt


def installed_profile(root,profile_sha256):
    root,_=local('curated_publication').configuration(root)
    if type(profile_sha256) is not str or not re.fullmatch('[0-9a-f]{64}',profile_sha256):raise ValueError('exact installed profile identity required')
    d=local('link_delivery');d.guard(root/'profiles');value=d.read(root/'profiles'/(profile_sha256+'.json'))
    if type(value) is not dict or set(value)!={'profile','receipt'}:raise ValueError('installed profile record differs')
    profile=validate_profile(value['profile']);receipt=value['receipt'];c=local('contract')
    if (c.digest(c.encoded(profile))!=profile_sha256 or type(receipt) is not dict or
            set(receipt)!={'contract','profile_sha256','owner_uid','recorded_at','profile_approval_recorded','human_authenticated','authority_granted'} or
            receipt['contract']!='engineering-curated-profile-receipt.v1' or receipt['profile_sha256']!=profile_sha256 or
            receipt['owner_uid']!=os.getuid() or receipt['profile_approval_recorded'] is not True or
            receipt['human_authenticated'] is not False or receipt['authority_granted'] is not False):
        raise ValueError('installed profile approval record differs')
    datetime.fromisoformat(receipt['recorded_at'].replace('Z','+00:00'))
    return value


def publish_bound(root,rows,profile_sha256,expected_head):
    profile=installed_profile(root,profile_sha256)['profile']
    return publish_profile(root,rows,profile,profile_sha256,expected_head,approve_profile=True)
