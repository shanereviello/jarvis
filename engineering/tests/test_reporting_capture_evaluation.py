"""Validate fixture provenance and format distinctions without a provider/runtime."""
import importlib.util
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('capture_fixture_test', ROOT / 'tools/rras_reporting/capture_evaluation.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


@pytest.mark.parametrize('style', ['legacy', 'thread-items', 'response-only'])
def test_fixture_has_same_visible_content_and_explicit_format(style, tmp_path):
    rows = m.events(tmp_path, style)
    assert rows[0]['type'] == 'session_meta' and rows[0]['payload']['cwd'] == str(tmp_path)
    assert rows[0]['payload']['model_provider'] == 'synthetic_no_calls'
    responses = [r for r in rows if r['type'] == 'response_item']
    assert [r['payload']['content'][0]['text'] for r in responses] == [m.PROMPT, m.ANSWER]
    ui = [r for r in rows if r['type'] == 'event_msg']
    assert len(ui) == (0 if style == 'response-only' else 2)


def test_capture_release_pins_are_not_floating():
    assert m.PINS['specstory'][0] == '2.17.0' and len(m.PINS['specstory'][1]) == 64
    assert m.PINS['entire'][0] == '0.13.1' and len(m.PINS['entire'][1]) == 64
