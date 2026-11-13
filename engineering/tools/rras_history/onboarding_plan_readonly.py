"""Read-only schema-5 onboarding migration plan; never opens a writable database."""
from contextlib import contextmanager
import importlib.util
import json
import os
from pathlib import Path
import sqlite3


def local(name):
    spec=importlib.util.spec_from_file_location('readonly_onboarding_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


class ReadOnlyStore:
    def __init__(self,path):
        self.path=Path(path)
        if os.getuid()==0 or not self.path.is_absolute() or self.path.resolve(strict=True)!=self.path:
            raise ValueError('unprivileged canonical history database required')

    @contextmanager
    def connection(self):
        db=sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True,timeout=10)
        try:
            db.execute('PRAGMA query_only=ON');db.execute('PRAGMA trusted_schema=OFF')
            yield db
        finally:db.close()


def plan(path):
    return local('onboarding_reservations').Reservations(ReadOnlyStore(path)).migration_plan()


if __name__=='__main__':
    import sys
    if len(sys.argv)!=2:raise SystemExit('One history database path is required.')
    try:print(json.dumps(plan(sys.argv[1]),sort_keys=True))
    except (ValueError,OSError,sqlite3.Error):raise SystemExit('Read-only onboarding plan refused; inspect history state.')
