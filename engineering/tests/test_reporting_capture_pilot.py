"""Single-session privacy boundary and hermetic invocation checks."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('capture_pilot_test', ROOT / 'tools/rras_reporting/capture_pilot.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
SESSION = '019a5e00-2222-7222-8222-222222222222'


@pytest.fixture
def transcript(tmp_path):
    path = tmp_path / 'selected.jsonl'
    rows = [dict(type='session_meta', payload=dict(id=SESSION)),
            dict(type='event_msg', payload=dict(type='user_message', message='SYNTHETIC-PROMPT')),
            dict(type='response_item', payload=dict(type='reasoning', summary='not a visible exchange'))]
    path.write_text(''.join(json.dumps(x) + '\n' for x in rows)); path.chmod(0o600)
    return path


def test_only_explicit_owned_session_and_complete_lines_are_read(transcript):
    original = transcript.read_bytes()
    with transcript.open('ab') as stream: stream.write(b'{"incomplete":')
    raw, rows = m.selected_source(transcript, SESSION)
    assert raw == original and m.visible(rows) == ['SYNTHETIC-PROMPT']
    with pytest.raises(ValueError): m.selected_source(transcript, '019a5e00-2222-7222-8222-222222222223')
    transcript.chmod(0o664)
    assert m.selected_source(transcript, SESSION)[0] == original
    transcript.chmod(0o666)
    with pytest.raises(ValueError): m.selected_source(transcript, SESSION)


def test_symlink_source_refused(transcript, tmp_path):
    link = tmp_path / 'alias'; link.symlink_to(transcript)
    with pytest.raises(ValueError): m.selected_source(link, SESSION)


def test_response_coverage_distinguishes_missing_visible_text_context_and_reasoning():
    def row(role, text, phase='unspecified'):
        return dict(type='response_item', payload=dict(type='message', role=role, phase=phase,
                    content=[dict(type='input_text' if role == 'user' else 'output_text', text=text)]))
    rows = [row('user', 'visible question'), row('assistant', 'missing result', 'final_answer'),
            row('user', '<external_codex_apps_open_page>synthetic</external_codex_apps_open_page>'),
            row('user', '<environment_context>synthetic</environment_context>'), row('assistant', 'excluded', 'analysis')]
    result = m.response_coverage(rows, 'visible question')
    assert result['unmatched_visible_or_unknown_messages'] == 1
    assert result['omitted_context_records'] == dict(app_navigation=1, environment_context=1)
    assert result['matched_message_counts'] == {'user:unspecified': 1}
    assert 'excluded' not in json.dumps(result)


def test_pilot_rejects_missing_authorization_before_reading_input(tmp_path):
    with pytest.raises(ValueError): m.run(tmp_path / 'state', tmp_path / 'missing', SESSION, None, None, '')
    assert not (tmp_path / 'state').exists()


def test_hermetic_pilot_keeps_all_outputs_private_and_checks_coverage(tmp_path, transcript, monkeypatch):
    binaries = {}
    for name in ('specstory', 'entire'):
        path = tmp_path / name; path.write_bytes(('synthetic-' + name).encode()); binaries[name] = path
        monkeypatch.setitem(m.PINS, name, hashlib.sha256(path.read_bytes()).hexdigest())
    seen = []
    def command(argv, **kwargs):
        seen.append((argv, kwargs))
        assert set(kwargs['env']) == {'HOME', 'PATH', 'LANG', 'CI', 'DO_NOT_TRACK'}
        assert kwargs['umask'] == 0o077 and kwargs['cwd'].name == 'isolated-repo'
        output = b''
        if Path(argv[0]).name == 'specstory':
            assert '--print' in argv and '--no-cloud-sync' in argv and argv[-1] == SESSION
            output = b'SYNTHETIC-PROMPT\n'
        if Path(argv[0]).name == 'entire' and argv[1] == 'enable':
            folder = kwargs['cwd'] / '.entire'; folder.mkdir()
            (folder / 'settings.local.json').write_text(json.dumps(dict(strategy_options=dict(push_sessions=False), telemetry=False)))
        if Path(argv[0]).name == 'entire' and argv[1] == 'session': output = json.dumps([dict(session_id=SESSION)]).encode()
        return subprocess.CompletedProcess(argv, 0, output, b'private synthetic command detail')
    monkeypatch.setattr(m.subprocess, 'run', command)
    state = tmp_path / 'pilot'
    result = m.run(state, transcript, SESSION, binaries['specstory'], binaries['entire'], 'Synthetic fixture authorization only')
    assert result['specstory']['ui_messages_exactly_present'] == 1
    assert result['entire']['session_tracked'] and result['isolated_collector_copy_unchanged']
    assert result['exact_source_snapshot_retained']
    assert (state / 'exact-source-snapshot.jsonl').read_bytes() == transcript.read_bytes()
    assert result['paid_model_calls'] == 0 and result['real_repository_hooks_changed'] is False
    assert state.stat().st_mode & 0o777 == 0o700
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in state.glob('command-*'))
    assert 'SYNTHETIC-PROMPT' not in json.dumps(result)
    with pytest.raises(FileExistsError):
        m.run(state, transcript, SESSION, binaries['specstory'], binaries['entire'], 'Same fixture')
