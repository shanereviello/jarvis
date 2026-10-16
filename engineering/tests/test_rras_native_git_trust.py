import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]/'tools/rras_native'
s=importlib.util.spec_from_file_location('activity',ROOT/'activity.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

def test_git_trust_is_exact_per_command_and_optional_locks_disabled(tmp_path):
    with patch.object(m.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout=b'fixture',stderr=b'')) as run:
        assert m.git(tmp_path,'rev-parse','HEAD')==b'fixture'
    args,options=run.call_args
    assert 'safe.directory='+str(tmp_path.resolve()) in args[0]
    assert 'safe.directory=*' not in args[0]
    assert options['env']['GIT_CONFIG_GLOBAL']=='/dev/null'
    assert options['env']['GIT_OPTIONAL_LOCKS']=='0'
    assert '--global' not in args[0]
