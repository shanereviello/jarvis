"""Explicit reservation upgrade preserves existing evidence and signed views."""
import pytest
from test_engineering_history_local import module,store
from test_history_projects import projects,REPO
from test_history_reporting import reporting,request
from test_history_evidence import evidence,upload,view


def test_v6_upgrade_preserves_prior_bytes_signed_snapshot_and_evidence(evidence,reporting,projects):
    old=view(projects)
    with evidence.store.connection() as db:
        tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        before={name:db.execute('SELECT * FROM "'+name+'"').fetchall() for name in tables}
        ddl=dict(db.execute("SELECT name,sql FROM sqlite_master WHERE sql IS NOT NULL"))
    reservations=module('onboarding_reservations').Reservations(evidence.store)
    plan=reservations.migration_plan()
    with pytest.raises(ValueError,match='exact migration plan'):reservations.migrate('0'*64)
    assert reservations.migrate(plan['expected_sha256'])['migrated']
    with evidence.store.connection() as db:
        assert db.execute('PRAGMA user_version').fetchone()[0]==6
        assert {name:db.execute('SELECT * FROM "'+name+'"').fetchall() for name in tables}==before
        current=dict(db.execute("SELECT name,sql FROM sqlite_master WHERE sql IS NOT NULL"))
        assert all(current[name]==sql for name,sql in ddl.items())
    assert projects.read(REPO,dict(view='project',project_id=old['project']['project_id'],snapshot=old['snapshot']))==old
    item=upload();assert evidence.upload(item)['inserted']
    assert evidence.read_blob(item['sha256'],item['byte_length'])
    assert reporting.submit(request(projects,'checkpoint.report'))['inserted']


def test_foreign_reserved_identity_cannot_be_claimed_by_old_mapping_api(evidence,reporting,projects):
    reservations=module('onboarding_reservations').Reservations(evidence.store)
    reservations.migrate(reservations.migration_plan()['expected_sha256'])
    candidate=request(projects,project_mapping=True)
    linear=candidate['body']['linear']
    reservations.reserve(linear['organization_id'],linear['project_id'],linear['team_id'],'prj_'+'f'*32,REPO)
    with pytest.raises(ValueError,match='planning binding unavailable'):
        reporting.submit(candidate)


def test_existing_project_mapping_cannot_be_reassigned_by_reservation(evidence,reporting,projects):
    mapping=request(projects,project_mapping=True);reporting.submit(mapping)
    reservations=module('onboarding_reservations').Reservations(evidence.store)
    reservations.migrate(reservations.migration_plan()['expected_sha256'])
    linear=mapping['body']['linear']
    with pytest.raises(ValueError,match='planning binding unavailable'):
        reservations.reserve(linear['organization_id'],linear['project_id'],linear['team_id'],'prj_'+'f'*32,REPO)
