import importlib.util
from pathlib import Path
import pytest

MODULE=Path(__file__).parents[1]/'tools/rras_reporting/codex_app_server_entry.py'
spec=importlib.util.spec_from_file_location('codex_app_server_entry',MODULE)
entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(entry)


def test_native_server_gets_only_the_single_systemd_api_credential(tmp_path,monkeypatch):
    credentials=tmp_path/'credentials';credentials.mkdir(mode=0o700)
    key=b'synthetic-api-key-0123456789abcdef'
    (credentials/'openai-api-key').write_bytes(key)
    home=tmp_path/'codex';home.mkdir(mode=0o700)
    monkeypatch.setenv('IRRELEVANT_PARENT_SECRET','must-not-be-inherited')
    result=entry.environment(credentials,'openai-api-key',home)
    assert result==dict(PATH='/usr/bin:/bin',HOME=str(home),CODEX_HOME=str(home),LANG='C.UTF-8',RRAS_OPENAI_API_KEY=key.decode())
    assert 'IRRELEVANT_PARENT_SECRET' not in result


def test_refuses_symlink_or_malformed_systemd_credential(tmp_path):
    credentials=tmp_path/'credentials';credentials.mkdir()
    home=tmp_path/'codex';home.mkdir()
    original=tmp_path/'original';original.write_bytes(b'x'*48)
    (credentials/'openai-api-key').symlink_to(original)
    with pytest.raises(ValueError):entry.environment(credentials,'openai-api-key',home)
    (credentials/'openai-api-key').unlink();(credentials/'openai-api-key').write_bytes(b'short')
    with pytest.raises(ValueError):entry.environment(credentials,'openai-api-key',home)
