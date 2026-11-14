import importlib.util
from pathlib import Path

import pytest
from test_history_projects import projects
from test_engineering_history_local import module,store


path=Path(__file__).resolve().parents[1]/'tools/rras_history/onboarding_plan_readonly.py'
spec=importlib.util.spec_from_file_location('readonly_plan_test',path)
readonly=importlib.util.module_from_spec(spec);spec.loader.exec_module(readonly)


def test_readonly_plan_matches_store_without_modifying_database(projects):
    store=projects.store
    for name,cls in [('scopes','Scopes'),('reporting','Reporting'),('evidence','Evidence')]:
        item=getattr(module(name),cls)(store);item.migrate(item.migration_plan()['expected_sha256'])
    expected=module('onboarding_reservations').Reservations(store).migration_plan()
    before=store.path.read_bytes();actual=readonly.plan(store.path)
    assert actual==expected and store.path.read_bytes()==before
    with readonly.ReadOnlyStore(store.path).connection() as db:
        with pytest.raises(Exception):db.execute('CREATE TABLE forbidden(value)')
