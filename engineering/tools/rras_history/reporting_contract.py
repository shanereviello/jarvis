"""Additive engineering-reporting.v1 metadata contract. No storage or authority.

Large export bytes are excluded: manifests reference bounded private chunks.
This contract does not extend legacy envelopes or silently upgrade any database.
"""
import importlib.util
from pathlib import Path
import re
from urllib.parse import urlsplit
from jsonschema import Draft202012Validator, FormatChecker


def local(name):
    spec = importlib.util.spec_from_file_location('reporting_contract_' + name, Path(__file__).with_name(name + '.py'))
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value); return value


def obj(**properties):
    return dict(type='object', properties=properties, required=list(properties), additionalProperties=False)


def text(maximum=4096): return dict(type='string', minLength=1, maxLength=maximum)
def nullable(value): return dict(anyOf=[value, dict(type='null')])
def array(value, maximum=64): return dict(type='array', items=value, maxItems=maximum)
def choices(*values): return dict(enum=list(values))
def pattern(value): return dict(type='string', pattern='^' + value + r'(?![\s\S])')
def ref(name): return {'$ref': '#/$defs/' + name}


SHA = pattern('[0-9a-f]{64}')
NAME = pattern('[A-Za-z0-9][A-Za-z0-9_.-]{0,95}')
UUID = dict(type='string', format='uuid', pattern='^[0-9a-f-]{36}(?![\\s\\S])')
VERSION = dict(type='integer', minimum=1, maximum=1000000)
UTC = dict(type='string', format='date-time', pattern='Z(?![\\s\\S])')
LINK = text(2048)
REF = obj(namespace=NAME, id=text(512), sha256=nullable(SHA))
SESSION = obj(namespace=NAME, id=text(512))
ACTOR = obj(role=choices('jarvis', 'codex', 'human', 'system', 'unknown'),
            runtime=NAME, source_actor_id=nullable(UUID))
REVISION = dict(version=VERSION, previous_sha256=nullable(SHA))

DEFS = dict(
    source=obj(kind=choices('agent_reported', 'human_reported', 'imported'), namespace=NAME, id=nullable(text(512))),
    scope=dict(anyOf=[obj(kind=dict(const='repository'), id=NAME),
                      obj(kind=dict(const='non_git'), id=dict(const='jarvis-non-git'))]),
    context=obj(project_id=pattern('prj_[0-9a-f]{32}'),
        architecture=obj(document_id=pattern('doc_[0-9a-f]{32}'), version=VERSION, markdown_sha256=SHA),
        work=nullable(obj(work_item_id=pattern('wrk_[0-9a-f]{32}'), work_revision_sha256=SHA, assignment_sha256=SHA))),
    mapping=obj(mapping_id=pattern('map_[0-9a-f]{32}'), **REVISION,
        kind=choices('project', 'execution', 'decision', 'grouping'), plan_id=nullable(NAME),
        linear=obj(organization_id=UUID, team_id=UUID, project_id=UUID, issue_id=nullable(UUID),
                   identifier=text(128), url=LINK), reason=text()),
    attempt=obj(attempt_id=pattern('att_[0-9a-f]{32}'), **REVISION,
        phase=choices('started', 'progress', 'paused', 'interrupted', 'failed', 'completed'), actor=ACTOR,
        coordinator=nullable(ACTOR), sessions=array(SESSION, 16), baseline_commit=nullable(pattern('[0-9a-f]{40}')),
        result=text(), references=array(REF)),
    session=obj(session=SESSION, relationship=choices('attached', 'resumed_from', 'compressed_from', 'continued_from', 'coordinated_by'),
        related_session=nullable(SESSION), attempt_id=nullable(pattern('att_[0-9a-f]{32}')), actor=ACTOR, reason=text()),
    session_metadata=obj(session_record_id=pattern('ses_[0-9a-f]{32}'),**REVISION,session=SESSION,actor=ACTOR,
        linear_agent_session_id=nullable(UUID),linear_agent_activity_id=nullable(UUID),oauth_client_id=nullable(pattern('(?:[0-9a-f]{32}|[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})')),
        native_session_tree_id=nullable(text(512)),parent_native_thread_id=nullable(text(512)),forked_from_native_thread_id=nullable(text(512)),
        host_identity=nullable(text(256)),workspace_identity=nullable(text(4096)),source_version=nullable(text(128)),
        model=nullable(text(128)),model_basis=choices('configured_thread','unknown'),
        tokens=nullable(obj(input=dict(type='integer',minimum=0),output=dict(type='integer',minimum=0),cached_input=nullable(dict(type='integer',minimum=0)))),
        cost_usd=nullable(dict(type='number',minimum=0)),limitations=array(text())),
    report=obj(report_id=pattern('rpt_[0-9a-f]{32}'), attempt_id=nullable(pattern('att_[0-9a-f]{32}')),
        observations=array(text()), alternatives_and_reasons=array(text()), changes=array(text()),
        validation=array(obj(result=choices('passed', 'failed', 'partial', 'not_run', 'unknown'),
                             description=text(), references=array(REF))),
        open_questions=array(text()), next_step=text(), references=array(REF)),
    observation=obj(object_kind=choices('project', 'issue', 'comment', 'document', 'agent_session', 'agent_activity'),
        organization_id=UUID, team_id=UUID, linear_project_id=UUID, object_id=UUID,
        source_updated_at=nullable(UTC), snapshot_sha256=SHA, snapshot_text=text(65536), references=array(REF)),
    handoff=obj(handoff_id=pattern('hof_[0-9a-f]{32}'), **REVISION,
        sender=ACTOR, recipient=ACTOR, state=choices('requested', 'acknowledged', 'completed', 'declined'),
        source_session=SESSION, target_session=nullable(SESSION), issue_id=UUID,
        requested_action=text(), result=nullable(text()), references=array(REF)),
    decision=obj(decision_id=pattern('dec_[0-9a-f]{32}'), **REVISION,
        kind=choices('architecture', 'deviation'), state=choices('requested', 'approved', 'rejected', 'withdrawn', 'unknown'),
        attributed_author=ACTOR, attribution=choices('agent_reported', 'imported_source', 'unknown'),
        source_reference=REF, decision_text=text(16384)),
    artifact=obj(artifact_id=pattern('cap_[0-9a-f]{32}'), **REVISION,
        session=SESSION, collector=NAME, collector_version=text(128),
        media_type=choices('text/plain', 'text/markdown', 'application/json', 'application/x-ndjson'),
        content_sha256=SHA, byte_length=dict(type='integer', minimum=0, maximum=64 * 1024 * 1024),
        chunks=array(obj(index=dict(type='integer', minimum=0, maximum=1023), sha256=SHA,
                         byte_length=dict(type='integer', minimum=1, maximum=65536)), 1024),
        source_range=obj(start=nullable(text(128)), end=nullable(text(128)), source_sha256=nullable(SHA)),
        completeness=choices('selected_range', 'partial', 'unknown'), gaps=array(text()),
        redaction_profile=NAME, source_created_at=nullable(UTC), source_updated_at=nullable(UTC)),
    association=obj(artifact_id=pattern('cap_[0-9a-f]{32}'), artifact_version=VERSION, manifest_sha256=SHA,
        previous_association_sha256=nullable(SHA), reason=text()),
    freshness=obj(source=SESSION, source_observed_at=nullable(UTC), cursor=nullable(text(512)),
        status=choices('current', 'pending', 'failed', 'unmapped', 'gap', 'unknown'),
        gaps=array(text()), detail=text()),
)

OPERATIONS = {'mapping.record': 'mapping', 'attempt.record': 'attempt', 'session.relate': 'session',
    'checkpoint.report': 'report', 'linear.observe': 'observation', 'handoff.record': 'handoff',
    'decision.observe': 'decision', 'artifact.record': 'artifact', 'artifact.associate': 'association',
    'source.observe': 'freshness','session.describe':'session_metadata'}

# Optional additive capture-time fact. Earlier retained manifests stay valid;
# receipt/import time and native source occurrence time remain separate.
DEFS['artifact']['properties']['captured_at']=UTC
DEFS['artifact']['properties']['authorization_reference']=text(2048)
DEFS['observation']['properties'].update(redaction_profile=NAME,source_snapshot_sha256=SHA,gaps=array(text()))
DEFS['report']['properties']['validation']['items']['properties'].update(
    criterion_id=nullable(NAME),command=nullable(text(4096)),code_commit=nullable(pattern('[0-9a-f]{40}')),
    environment=nullable(text(1024)),output_sha256=nullable(SHA))
DEFS['attempt']['properties'].update(previous_attempt_id=nullable(pattern('att_[0-9a-f]{32}')),
    managed_task_id=nullable(text(256)),managed_run_id=nullable(text(256)),branch=nullable(text(256)),
    worktree_identity=nullable(text(4096)),started_at=nullable(UTC),ended_at=nullable(UTC))

SCHEMA = dict(obj(contract=dict(const='engineering-reporting.v1'), operation=choices(*OPERATIONS),
    client_event_key=text(128), expected_head=nullable(SHA), scope=ref('scope'), context=nullable(ref('context')),
    source=ref('source'), occurred_at=nullable(UTC), body=dict(type='object')),
    **{'$schema': 'https://json-schema.org/draft/2020-12/schema', '$id': 'urn:rras:engineering-reporting:v1', '$defs': DEFS})
# Build conditional bodies without a free-form metadata escape hatch.
SCHEMA['allOf'] = [{'if': {'properties': {'operation': {'const': operation}}},
                    'then': {'properties': {'body': ref(body)}}} for operation, body in OPERATIONS.items()]


def validate(value):
    c = local('contract'); value = c.decode(c.encoded(value))
    Draft202012Validator(SCHEMA, format_checker=FormatChecker()).validate(value)
    def inspect(item):
        if isinstance(item, str) and ('\0' in item or not item.strip()): raise ValueError('nonempty text without NUL required')
        if isinstance(item, dict):
            for key, child in item.items(): inspect(key); inspect(child)
        if isinstance(item, list):
            for child in item: inspect(child)
    inspect(value)
    op, body, context = value['operation'], value['body'], value['context']
    if context is None and op not in ('artifact.record', 'source.observe', 'linear.observe','session.describe'):
        raise ValueError('explicit project/architecture context required')
    if op in ('attempt.record', 'session.relate', 'checkpoint.report', 'handoff.record') and context['work'] is None:
        raise ValueError('explicit work context required')
    if 'version' in body and ((body['version'] == 1) != (body['previous_sha256'] is None)):
        raise ValueError('first version or exact predecessor required')
    if value['expected_head'] != body.get('previous_sha256', body.get('previous_association_sha256')):
        raise ValueError('exact predecessor request digest required; append-only observations have no prior head')
    if op == 'mapping.record':
        execution = body['kind'] == 'execution'
        if execution != (context['work'] is not None) or execution != (body['plan_id'] is not None):
            raise ValueError('only execution mappings count as work and require plan IDs')
        if (body['kind'] == 'project') != (body['linear']['issue_id'] is None):
            raise ValueError('project mappings have no execution/decision/grouping issue')
        url = urlsplit(body['linear']['url'])
        if (url.scheme != 'https' or url.netloc != 'linear.app' or url.query or url.fragment or
                any(ord(ch) <= 32 or ch == '\\' for ch in body['linear']['url'])):
            raise ValueError('credential-free Linear URL required')
    if op == 'handoff.record':
        if {body['sender']['role'], body['recipient']['role']} != {'jarvis', 'codex'}:
            raise ValueError('handoff requires distinct named agents')
        if body['state'] in ('acknowledged', 'completed') and body['target_session'] is None:
            raise ValueError('recipient acknowledgment requires actual session')
    if op == 'session.relate' and ((body['relationship'] == 'attached') != (body['related_session'] is None)):
        raise ValueError('lineage names its actual related session')
    if op=='session.describe' and ((body['model'] is None)!=(body['model_basis']=='unknown')):
        raise ValueError('known configured model or explicit unknown required')
    if op == 'attempt.record' and value['scope']['kind'] == 'non_git' and body['baseline_commit'] is not None:
        raise ValueError('non-Git attempt has no Git baseline')
    if op == 'artifact.record':
        if [part['index'] for part in body['chunks']] != list(range(len(body['chunks']))):
            raise ValueError('contiguous immutable chunk indices required')
        if sum(part['byte_length'] for part in body['chunks']) != body['byte_length']:
            raise ValueError('chunk lengths must equal manifest length')
        if body['byte_length'] == 0 and body['content_sha256'] != c.digest(b''):
            raise ValueError('empty artifact has exact empty-content digest')
        if body['completeness'] == 'partial' and not body['gaps']: raise ValueError('partial capture names its gap')
    if op == 'linear.observe' and c.digest(body['snapshot_text'].encode()) != body['snapshot_sha256']:
        raise ValueError('exact observed snapshot digest required')
    # Source times are observations, never receipt times or independent approval.
    for stamp in [value['occurred_at']] + ([body.get(k) for k in ('source_updated_at', 'source_created_at', 'source_observed_at','captured_at','started_at','ended_at')]):
        if stamp is not None and not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z', stamp):
            raise ValueError('exact UTC source time required')
    return value
