import importlib.util
from pathlib import Path
import sqlite3
import pytest

path=Path(__file__).resolve().parents[1]/'tools/rras_reporting/onboarding_service_entry.py'
spec=importlib.util.spec_from_file_location('planning_entry_fixture',path)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_initialize_only_new_private_state_and_preserves_existing(tmp_path):
    root=tmp_path/'planning';result=m.initialize(root)
    assert result==dict(initialized=True,models_started=0,listener_started=False)
    with sqlite3.connect(root/'planning.sqlite3') as db:
        names={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {'planning_turns','planning_policy','planning_sessions','issue_creation'}<=names
    with pytest.raises(ValueError):m.initialize(root)
    assert (root/'planning.sqlite3').is_file()
