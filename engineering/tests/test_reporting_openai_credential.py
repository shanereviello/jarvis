import importlib.util
from pathlib import Path
import pytest

MODULE=Path(__file__).parents[1]/'tools/rras_reporting/prepare_openai_credential.py'
spec=importlib.util.spec_from_file_location('prepare_openai_credential',MODULE)
credential=importlib.util.module_from_spec(spec);spec.loader.exec_module(credential)


def test_extracts_only_one_bounded_api_key_without_shell_evaluation():
    key=b'sk-test-$literal#fragment-0123456789abcdef'
    raw=b'# private values omitted\nOTHER_SECRET=not-for-codex\nexport OPENAI_API_KEY="'+key+b'"\n'
    assert credential.parse(raw)==key


@pytest.mark.parametrize('raw',[
    b'OTHER_SECRET='+b'x'*48+b'\n',
    b'OPENAI_API_KEY='+b'x'*48+b'\nOPENAI_API_KEY='+b'y'*48+b'\n',
    b'OPENAI_API_KEY="unterminated',
    b'OPENAI_API_KEY='+b'x'*16+b'\n',
])
def test_rejects_missing_ambiguous_malformed_or_unbounded_key(raw):
    with pytest.raises(ValueError):credential.parse(raw)


def test_does_not_parse_unbounded_or_non_utf8_env():
    with pytest.raises(ValueError):credential.parse(b'x'*(1024*1024+1))
    with pytest.raises(UnicodeDecodeError):credential.parse(b'OPENAI_API_KEY=\xff')


def test_ignores_similarly_named_variables():
    key=b'x'*48
    assert credential.parse(b'OPENAI_API_KEY_ROTATION='+b'y'*48+b'\nOPENAI_API_KEY='+key+b'\n')==key
