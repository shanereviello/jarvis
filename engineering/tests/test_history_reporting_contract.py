"""Typed relationship boundaries; these tests do not claim storage or RPC delivery."""
import copy
import uuid
import pytest
from jsonschema import ValidationError
from test_engineering_history_local import module

m = module('reporting_contract')
c = module('contract')
def ident(n): return str(uuid.UUID(int=n))
def actor(role='codex'): return dict(role=role, runtime='fixture', source_actor_id=None)
def session(name='fixture'): return dict(namespace='fixture', id=name)
def context():
    return dict(project_id='prj_' + '1' * 32,
        architecture=dict(document_id='doc_' + '2' * 32, version=3, markdown_sha256='3' * 64),
        work=dict(work_item_id='wrk_' + '4' * 32, work_revision_sha256='5' * 64, assignment_sha256='6' * 64))


def request(operation='mapping.record'):
    revision = dict(version=1, previous_sha256=None)
    bodies = {
        'mapping.record': dict(mapping_id='map_' + '1' * 32, **revision, kind='execution', plan_id='SHRR-04',
            linear=dict(organization_id=ident(1), team_id=ident(2), project_id=ident(3), issue_id=ident(4),
                        identifier='REV-49', url='https://linear.app/fixture/issue/REV-49'), reason='Explicit execution mapping'),
        'attempt.record': dict(attempt_id='att_' + '1' * 32, **revision, phase='started', actor=actor(),
            coordinator=None, sessions=[session()], baseline_commit='7' * 40, result='Start claimed; not a work outcome', references=[]),
        'session.relate': dict(session=session(), relationship='resumed_from', related_session=session('previous'),
            attempt_id=None, actor=actor(), reason='Retain actual linked continuation'),
        'session.describe':dict(session_record_id='ses_'+'1'*32,**revision,session=session(),actor=actor(),
            linear_agent_session_id=ident(5),linear_agent_activity_id=None,oauth_client_id=None,
            native_session_tree_id=None,parent_native_thread_id=None,forked_from_native_thread_id=None,
            host_identity=None,workspace_identity=None,source_version=None,model=None,model_basis='unknown',
            tokens=None,cost_usd=None,limitations=['Synthetic fixture; unknown values stay unknown.']),
        'checkpoint.report': dict(report_id='rpt_' + '1' * 32, attempt_id=None, observations=['Fixture observation'],
            alternatives_and_reasons=['Rejected missing association'], changes=[], validation=[],
            open_questions=[], next_step='Exercise receipt replay', references=[]),
        'linear.observe': dict(object_kind='issue', organization_id=ident(1), team_id=ident(2), linear_project_id=ident(3),
            object_id=ident(4), source_updated_at=None, snapshot_sha256=c.digest(b'fixture snapshot'), snapshot_text='fixture snapshot', references=[]),
        'handoff.record': dict(handoff_id='hof_' + '1' * 32, **revision, sender=actor('jarvis'), recipient=actor(),
            state='requested', source_session=session('sender'), target_session=None, issue_id=ident(4),
            requested_action='Investigate the same mapped work', result=None, references=[]),
        'decision.observe': dict(decision_id='dec_' + '1' * 32, **revision, kind='architecture', state='approved',
            attributed_author=actor('human'), attribution='agent_reported',
            source_reference=dict(namespace='fixture', id='operator-source', sha256=None),
            decision_text='Agent-reported transcription; no authenticated authority inferred'),
        'artifact.record': dict(artifact_id='cap_' + '1' * 32, **revision, session=session(), collector='specstory',
            collector_version='2.17.0', media_type='text/markdown', content_sha256=c.digest(b'fixture'), byte_length=7,
            chunks=[dict(index=0, sha256=c.digest(b'fixture'), byte_length=7)],
            source_range=dict(start='1', end='2', source_sha256=None), completeness='partial',
            gaps=['Synthetic selected range only'], redaction_profile='fixture', source_created_at=None, source_updated_at=None),
        'artifact.associate': dict(artifact_id='cap_' + '1' * 32, artifact_version=1, manifest_sha256='7' * 64,
            previous_association_sha256=None, reason='Correct association append; original remains'),
        'source.observe': dict(source=session(), source_observed_at=None, cursor=None,
            status='pending', gaps=['Delivery pending'], detail='No model launched'),
    }
    return dict(contract='engineering-reporting.v1', operation=operation, client_event_key='fixture-reporting',
                expected_head=None, scope=dict(kind='repository', id='jarvis'), context=context(),
                source=dict(kind='agent_reported', namespace='fixture', id='reported-author'), occurred_at=None,
                body=copy.deepcopy(bodies[operation]))


@pytest.mark.parametrize('operation', list(m.OPERATIONS))
def test_each_typed_operation_has_an_explicit_bounded_envelope(operation):
    original = request(operation); result = m.validate(original)
    assert result == original and result is not original


@pytest.mark.parametrize('change', ['authority', 'body_extra', 'raw_export', 'newline_digest', 'wrong_category', 'boolean_version'])
def test_unreviewed_fields_and_malformed_scope_or_identity_refused(change):
    value = request()
    if change == 'authority': value['authenticated_human_approval'] = True
    elif change == 'body_extra': value['body']['automatically_launch'] = True
    elif change == 'raw_export': value['body']['transcript'] = 'not allowed in a metadata request'
    elif change == 'newline_digest': value['context']['work']['work_revision_sha256'] += '\n'
    elif change == 'wrong_category': value['scope'] = dict(kind='non_git', id='other')
    else: value['body']['version'] = True
    with pytest.raises((ValueError, ValidationError)): m.validate(value)


def test_decision_issue_cannot_inflate_execution_count_or_claim_work():
    value = request(); value['body'].update(kind='decision', plan_id=None)
    with pytest.raises(ValueError): m.validate(value)
    value['context']['work'] = None
    assert m.validate(value)['body']['kind'] == 'decision'
    value['body'].update(kind='project', linear=dict(value['body']['linear'], issue_id=None))
    assert m.validate(value)['context']['work'] is None


@pytest.mark.parametrize('operation', ['artifact.record', 'source.observe', 'linear.observe'])
def test_pending_capture_and_observations_can_remain_unmapped(operation):
    value = request(operation); value['context'] = None
    assert m.validate(value)['context'] is None
    value = request('checkpoint.report'); value['context'] = None
    with pytest.raises(ValueError): m.validate(value)


def test_revisions_pin_the_exact_predecessor_and_never_reuse_version_one():
    value = request('attempt.record'); value['body'].update(version=2, previous_sha256='8' * 64)
    with pytest.raises(ValueError): m.validate(value)
    value['expected_head'] = '8' * 64
    assert m.validate(value)['body']['version'] == 2
    value['body']['version'] = 1
    with pytest.raises(ValueError): m.validate(value)


def test_same_agent_handoff_and_unbound_acknowledgment_refused():
    value = request('handoff.record'); value['body']['sender'] = actor()
    with pytest.raises(ValueError): m.validate(value)
    value = request('handoff.record'); value['body']['state'] = 'acknowledged'
    with pytest.raises(ValueError): m.validate(value)
    value['body']['target_session'] = session('recipient')
    assert m.validate(value)['body']['state'] == 'acknowledged'


def test_export_chunks_require_exact_ranges_lengths_and_explicit_gaps():
    value = request('artifact.record'); value['body']['chunks'][0]['index'] = 1
    with pytest.raises(ValueError): m.validate(value)
    value = request('artifact.record'); value['body']['byte_length'] += 1
    with pytest.raises(ValueError): m.validate(value)
    value = request('artifact.record'); value['body']['gaps'] = []
    with pytest.raises(ValueError): m.validate(value)


def test_observation_content_is_bound_to_exact_digest_and_source_time_is_separate():
    value = request('linear.observe'); value['body']['snapshot_text'] += ' changed'
    with pytest.raises(ValueError): m.validate(value)
    value = request('linear.observe'); value['body']['source_updated_at'] = '2026-11-07T12:00:00Z'
    assert m.validate(value)['occurred_at'] is None


def test_nongit_attempt_cannot_introduce_a_commit_baseline():
    value = request('attempt.record'); value['scope'] = dict(kind='non_git', id='jarvis-non-git')
    with pytest.raises(ValueError): m.validate(value)
    value['body']['baseline_commit'] = None
    assert m.validate(value)['body']['baseline_commit'] is None


def test_nul_duplicate_and_oversized_metadata_are_refused():
    value = request('checkpoint.report'); value['body']['next_step'] = 'bad\0text'
    with pytest.raises(ValueError): m.validate(value)
    with pytest.raises(ValueError): c.decode(b'{"contract":1,"contract":2}')
    value = request('checkpoint.report'); value['body']['observations'] = ['x' * 4096] * 64
    with pytest.raises(ValueError): m.validate(value)
