"""Passive contract/history tests: no repository, service or model execution."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('records', ROOT/'tools/rras_native/workflow_records.py')
r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)


def history(name='jarvis-interactive.json'):
    return json.loads((ROOT/'contracts/examples'/name).read_text())


def rebind(rows):
    rows[1]['registration_sha256'] = r.record_digest(rows[0])
    rows[2]['registration_sha256'] = r.record_digest(rows[0])
    rows[2]['work_item_sha256'] = r.record_digest(rows[1])
    rows[3]['work_item_sha256'] = r.record_digest(rows[1])


def next_event(rows):
    event = copy.deepcopy(rows[-1])
    event.update(event_id='evt_'+'f'*32, sequence=2,
                 previous_event_sha256=r.record_digest(rows[-1]),
                 event_type='validation.finished', outcome='failed', summary='Fixture validation failure.')
    return event


def test_schema_is_valid_and_two_repositories_modes_share_contract():
    Draft202012Validator.check_schema(json.loads(r.SCHEMA.read_text()))
    a,b=history(),history('library-managed.json')
    assert a[0]['repository_id']!=b[0]['repository_id']
    assert r.validate_history(list(reversed(a+b)))=={'records':8,'work_items':2,'attempts':2,'event_streams':2}
    assert all(x['provenance']['kind']=='imported' for x in a+b)


@pytest.mark.parametrize('value',[True,0,2,'1'])
def test_version_requires_actual_integer_one(value):
    row=history()[1];row['schema_version']=value
    with pytest.raises(ValueError):r.validate_record(row)


@pytest.mark.parametrize('extra',['execution_authorized','publication_authorized','credential','raw_log','status'])
def test_unrecognized_authority_or_inline_payload_fields_refused(extra):
    row=history()[3];row[extra]=True
    with pytest.raises(ValueError,match='invalid workflow record'):r.validate_record(row)


@pytest.mark.parametrize('remote',['https://token@example.com/repo','https://example.com/repo?token=secret','ssh://git:password@example.com/repo','https://example.com/repo#secret'])
def test_credential_bearing_remote_shapes_refused(remote):
    row=history()[0];row['source']['remote']=remote
    with pytest.raises(ValueError):r.validate_record(row)


@pytest.mark.parametrize('remote',[None,'https://example.com/team/repo.git','git@example.com:team/repo.git','deploy@example.com:team/repo.git','ssh://deploy@example.com/team/repo'])
def test_local_or_ordinary_ssh_https_repository_registration(remote):
    row=history()[0];row['source']['remote']=remote
    assert r.validate_record(row)==row


@pytest.mark.parametrize('path',['../secret','src/../secret','/etc/passwd','src//file','src\\file','./file'])
def test_noncanonical_requested_paths_refused(path):
    row=history()[1];row['requested_paths']=[path]
    with pytest.raises(ValueError):r.validate_record(row)


def test_utc_timestamp_and_recipe_identity_are_required():
    row=history()[0];row['created_at']='2026-02-30T12:00:00Z'
    with pytest.raises(ValueError):r.validate_record(row)
    row=history()[0];row['validation_recipes'][0]['execution_identity']='root'
    with pytest.raises(ValueError):r.validate_record(row)
    row=history()[0];row['validation_recipes'][0]['argv'][0]='python'
    with pytest.raises(ValueError):r.validate_record(row)


def test_hash_is_key_order_independent_and_null_unknowns_survive():
    rows=history();rows[1]['baseline']=None;rows[1]['validation_id']=None
    rows[2]['baseline']=None;rebind(rows)
    assert r.record_digest(rows[1])==r.record_digest(dict(reversed(list(rows[1].items()))))
    assert r.validate_history(rows)['records']==4


def test_sha256_git_ids_are_recordable_without_enabling_current_launcher():
    rows=history();rows[0]['source']['object_format']='sha256'
    with pytest.raises(ValueError,match='Git object'):rebind(rows);r.validate_history(rows)
    rows[1]['baseline']['commit']='b'*64;rows[2]['baseline']=copy.deepcopy(rows[1]['baseline']);rebind(rows)
    assert r.validate_history(rows)['records']==4


@pytest.mark.parametrize('change',['missing_registration','wrong_repository','wrong_work','duplicate_identity','duplicate_attempt'])
def test_complete_history_refuses_broken_associations(change):
    rows=history()
    if change=='missing_registration':rows.pop(0)
    elif change=='wrong_repository':rows[2]['repository_id']='someone_else'
    elif change=='wrong_work':rows[3]['work_item_id']='wrk_'+'c'*32
    elif change=='duplicate_identity':rows.append(copy.deepcopy(rows[0]))
    else:
        other=copy.deepcopy(rows[2]);other['attempt_id']='att_'+'b'*32;rows.append(other)
    with pytest.raises(ValueError):r.validate_history(rows)


def test_event_chain_corrections_and_input_order():
    rows=history();event=next_event(rows);event['corrects_event_id']=rows[3]['event_id'];rows.append(event)
    assert r.validate_history(list(reversed(rows)))['records']==5
    event['corrects_event_id']='evt_'+'b'*32
    with pytest.raises(ValueError,match='earlier event'):r.validate_history(rows)


@pytest.mark.parametrize('mutation',['gap','duplicate_sequence','wrong_parent','changed_prior_event','unknown_attempt'])
def test_event_stream_refuses_inconsistent_or_disconnected_history(mutation):
    rows=history();rows.append(next_event(rows))
    if mutation=='gap':rows[-1]['sequence']=3
    elif mutation=='duplicate_sequence':rows[-1]['sequence']=1;rows[-1]['previous_event_sha256']=None
    elif mutation=='wrong_parent':rows[-1]['previous_event_sha256']='0'*64
    elif mutation=='changed_prior_event':rows[3]['summary']='changed without updating chain'
    else:rows[-1]['attempt_id']='att_'+'c'*32
    with pytest.raises(ValueError):r.validate_history(rows)


def test_revision_retains_old_attempt_and_new_revision_has_new_digest():
    rows=history();new=copy.deepcopy(rows[1]);new.update(revision=2,supersedes_sha256=r.record_digest(rows[1]),objective='Revised fixture objective')
    rows.append(new);assert r.validate_history(rows)['records']==5
    assert rows[2]['work_item_sha256']==r.record_digest(rows[1])!=r.record_digest(new)
    new['revision']=3
    with pytest.raises(ValueError,match='revision chain'):r.validate_history(rows)


def test_delegated_and_human_reported_release_are_only_passive_data():
    rows=history();rows[1]['mode']=rows[2]['mode']='delegated';rebind(rows)
    rows[3].update(event_type='change.merged',outcome='succeeded',summary='Unverified human-reported historical merge')
    rows[3]['provenance']['kind']='human_reported'
    assert r.validate_history(rows)['records']==4
    assert rows[2]['authorization_reference'] is None and rows[2]['delegation_reference'] is None
    assert rows[3]['provenance']['kind']=='human_reported'  # never promoted to verified


def test_actual_nul_is_refused_but_literal_escaped_text_can_be_recorded():
    row=history()[1];row['objective']='bad'+chr(0)+'text'
    with pytest.raises(ValueError,match='NUL'):r.validate_record(row)
    row['objective']=r'Document the literal escape \u0000 without embedding NUL'
    assert r.validate_record(row)==row


def test_git_metadata_denial_and_recipe_uniqueness_are_required():
    row=history()[0];row['path_policy']['denied_roots']=[]
    with pytest.raises(ValueError):r.validate_record(row)
    row=history()[0];row['validation_recipes'].append(copy.deepcopy(row['validation_recipes'][0]))
    with pytest.raises(ValueError,match='duplicate validation'):r.validate_record(row)


def test_attempt_cannot_silently_change_a_known_work_baseline():
    rows=history();rows[2]['baseline']=copy.deepcopy(rows[2]['baseline']);rows[2]['baseline']['commit']='c'*40
    with pytest.raises(ValueError,match='baseline snapshot'):r.validate_history(rows)


def test_attempt_authorization_reference_namespace_is_not_interchangeable():
    row=history()[2];row['authorization_reference']={'namespace':'pull_request','id':'123'}
    with pytest.raises(ValueError,match='namespace'):r.validate_record(row)


def test_artifact_identity_cannot_be_repointed_or_reclassified_silently():
    rows=history();artifact={'artifact_id':'art_'+'e'*32,'sha256':'d'*64,'media_type':'application/json','visibility':'operator_only','purpose':'validation'}
    rows[3]['artifacts']=[artifact];event=next_event(rows);rows.append(event)
    assert r.validate_history(rows)['records']==5
    rows[-1]['artifacts'][0]['visibility']='public_review'
    with pytest.raises(ValueError,match='artifact identity'):r.validate_history(rows)


def test_human_deliverable_acceptance_is_structured_and_separate_from_validation():
    row=history()[3];row.update(event_type='decision.recorded',outcome='approved')
    with pytest.raises(ValueError,match='decision subject'):r.validate_record(row)
    row['decision_subject']='deliverable_acceptance'
    assert r.validate_record(row)==row
    row['event_type']='validation.finished'
    with pytest.raises(ValueError,match='decision subject'):r.validate_record(row)


def test_identifier_and_digest_patterns_reject_terminal_newlines():
    row=history()[1];row['repository_id']+='\n'
    with pytest.raises(ValueError):r.validate_record(row)
    row=history()[1];row['registration_sha256']+='\n'
    with pytest.raises(ValueError):r.validate_record(row)
