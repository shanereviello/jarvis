import importlib.util
from pathlib import Path
import sqlite3

import pytest


path=Path(__file__).resolve().parents[1]/'tools/rras_reporting/hermes_planning_journal.py'
spec=importlib.util.spec_from_file_location('hermes_journal_test',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_private_journal_exclusivity_and_uncertain_recovery(tmp_path):
    root=tmp_path/'journal';assert module.initialize(root)['initialized']
    with module.open_journal(root) as connection:
        with pytest.raises(BlockingIOError):
            with module.open_journal(root):pass
        with connection() as db:
            db.execute("INSERT INTO issue_creation VALUES('org','project','plan','hash','creating',NULL)")
            db.commit()
    with module.open_journal(root) as connection:
        with connection() as db:assert db.execute('SELECT state FROM issue_creation').fetchone()==('uncertain',)
    with pytest.raises(ValueError):module.initialize(root)
