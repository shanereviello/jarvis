"""Model-free comparison of pinned third-party capture releases on synthetic data.

No installation, provider calls, real agent history, login, remote, or Git push.
Run inside the normal network-restricted development sandbox.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

PINS = {
    'specstory': ('2.17.0', '5e4b0275a0f71ad0825207688ba7c8c844ad301326a94e814fd59f7e20a90b69'),
    'entire': ('0.13.1', 'c7afbecd5e18bee7a97b69ec318ff9f14033994eae309746c98ec7eed9c33048'),
}
SESSION = '019a5e00-2222-7222-8222-222222222222'
PROMPT = 'SYNTHETIC-REPORTING: investigate capture without changing code.'
ANSWER = 'SYNTHETIC-RESULT: the first approach failed; use explicit work IDs.'
FOLLOWUP = 'SYNTHETIC-RESUME: preserve the failure and continue the same work.'


def events(repo, style='legacy'):
    rows = [dict(timestamp='2026-11-07T12:00:00Z', type='session_meta', payload=dict(
        id=SESSION, timestamp='2026-11-07T12:00:00Z', cwd=str(repo), originator='synthetic_fixture',
        cli_version='0.149.0', source='cli', model_provider='synthetic_no_calls'))]
    for index, (role, text) in enumerate([('user', PROMPT), ('assistant', ANSWER)], 1):
        timestamp = f'2026-11-07T12:00:0{index}Z'
        rows.append(dict(timestamp=timestamp, type='response_item', payload=dict(type='message', role=role,
            content=[dict(type='input_text' if role == 'user' else 'output_text', text=text)])))
        if style == 'legacy':
            rows.append(dict(timestamp=timestamp, type='event_msg', payload=dict(
                type='user_message' if role == 'user' else 'agent_message', message=text)))
        elif style == 'thread-items':
            rows.append(dict(timestamp=timestamp, type='event_msg', payload=dict(type='item_completed', item=dict(
                type='UserMessage' if role == 'user' else 'AgentMessage', content=[dict(type='text', text=text)]))))
    return rows


def run(root, specstory, entire):
    root = Path(root).resolve()
    root.mkdir(mode=0o700, parents=True)  # Refuse reuse; keep prior results.
    home = root / 'isolated-home'; home.mkdir(mode=0o700)
    repo = root / 'synthetic-repo'; repo.mkdir(mode=0o700)
    env = {'HOME': str(home), 'PATH': str(entire.parent) + ':/usr/bin:/bin',
           'LANG': 'C.UTF-8', 'CI': '1', 'DO_NOT_TRACK': '1'}
    commands = []

    def command(argv, data=None, timeout=25):
        result = subprocess.run([str(v) for v in argv], input=data, cwd=repo, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)
        commands.append(dict(argv=[str(v) for v in argv], exit_code=result.returncode))
        return result

    for args in [('init', '-q'), ('config', 'user.name', 'Synthetic Capture Evaluation'),
                 ('config', 'user.email', 'synthetic@example.invalid'),
                 ('commit', '--allow-empty', '-qm', 'Synthetic fixture baseline')]:
        assert command(['git', *args]).returncode == 0
    sessions = home / '.codex/sessions/2026/11/07'; sessions.mkdir(parents=True)
    rollout = sessions / f'rollout-2026-11-07T12-00-00-{SESSION}.jsonl'
    flags = ['--no-cloud-sync', '--no-usage-analytics', '--no-version-check',
             '--no-telemetry-prompts', '--no-stats']
    cases = {}
    for style in ['legacy', 'thread-items', 'response-only']:
        rollout.write_text(''.join(json.dumps(row) + '\n' for row in events(repo, style)))
        result = command([specstory, 'sync', 'codex', *flags, '--print', '-s', SESSION])
        output = result.stdout.decode('utf-8')
        (root / ('specstory-' + style + '.md')).write_text(output)
        cases[style] = dict(exit_code=result.returncode,
            prompt_retained=PROMPT in output, answer_retained=ANSWER in output)
    # Restore a supported UI stream for incremental export and watcher testing.
    rollout.write_text(''.join(json.dumps(row) + '\n' for row in events(repo)))
    exports = root / 'private-exports'
    result = command([specstory, 'sync', 'codex', *flags, '--output-dir', exports])
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in exports.glob('*.md')}
    repeat = command([specstory, 'sync', 'codex', *flags, '--output-dir', exports])
    after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in exports.glob('*.md')}
    stable_export = before == after and bool(before) and repeat.returncode == 0
    watch = subprocess.Popen([str(specstory), 'watch', 'codex', *flags, '--output-dir', str(exports), '--silent'],
        cwd=repo, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    watched = False
    try:
        # Give the watcher time to subscribe; append instead of replacing the source.
        time.sleep(1)
        with rollout.open('a') as stream:
            stream.write(json.dumps(dict(timestamp='2026-11-07T12:01:00Z', type='event_msg',
                payload=dict(type='user_message', message=FOLLOWUP))) + '\n')
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and watch.poll() is None:
            if any(FOLLOWUP in p.read_text() for p in exports.glob('*.md')):
                watched = True; break
            time.sleep(.2)
    finally:
        watch.terminate()
        try: watch.wait(timeout=3)
        except subprocess.TimeoutExpired: watch.kill(); watch.wait(timeout=3)
    native_sha = hashlib.sha256(rollout.read_bytes()).hexdigest()
    enabled = command([entire, 'enable', '--agent', 'codex', '--local',
                       '--skip-push-sessions', '--telemetry=false', '--yes'])
    (root / 'entire-enable.txt').write_bytes(enabled.stdout + enabled.stderr)
    settings_path = repo / '.entire/settings.local.json'
    settings = json.loads(settings_path.read_text()) if settings_path.exists() else {}
    # Explicitly exercise native hook inputs, not a paid Codex turn.
    hook_results = []
    for verb, event in [('session-start', 'SessionStart'), ('user-prompt-submit', 'UserPromptSubmit'),
                        ('stop', 'Stop'), ('session-end', 'SessionEnd')]:
        payload = dict(session_id=SESSION, transcript_path=str(rollout), cwd=str(repo), hook_event_name=event,
            source='startup', prompt=PROMPT, last_assistant_message=ANSWER, reason='other')
        result = command([entire, 'hooks', 'codex', verb], json.dumps(payload).encode())
        hook_results.append(dict(event=event, exit_code=result.returncode))
    inventory = command([entire, 'session', 'list', '--json'])
    tracked = json.loads(inventory.stdout) if inventory.returncode == 0 else []
    refs = command(['git', 'for-each-ref', 'refs/entire', '--format=%(refname)']).stdout.decode().splitlines()
    hook_cfg = repo / '.codex/hooks.json'
    hooks = json.loads(hook_cfg.read_text()) if hook_cfg.exists() else {}
    report = dict(contract='reporting-capture-evaluation.v1', synthetic_only=True, paid_model_calls=0,
        real_credentials_used=False, real_sessions_read=False, real_collector_enabled=False,
        network_boundary='executed in development sandbox; flags disable cloud sync/analytics; no network packet audit claimed',
        versions={key: value[0] for key, value in PINS.items()},
        executable_sha256={key: hashlib.sha256(path.read_bytes()).hexdigest() for key, path in [('specstory', specstory), ('entire', entire)]},
        specstory=dict(cases=cases, repeated_export_stable=stable_export, background_append_captured=watched,
            local_export_outside_source=True),
        entire=dict(enable_exit_code=enabled.returncode, settings=settings, installed_hook_events=sorted(hooks.get('hooks', {})),
            hooks=hook_results, session_tracked=any(row.get('session_id') == SESSION for row in tracked),
            persistent_refs_without_code_commit=refs),
        native_source_unchanged_by_collectors=hashlib.sha256(rollout.read_bytes()).hexdigest() == native_sha,
        fixture_remotes=command(['git', 'remote']).stdout.decode().splitlines(),
        untested=['actual installed Codex desktop and managed runtime', 'Mac binary', 'compressed/rotated sessions',
                  'native Hermes capture', 'real-session pilot', 'runtime inference and live webhook'], commands=commands)
    (root / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--specstory', type=Path, required=True)
    parser.add_argument('--entire', type=Path, required=True)
    args = parser.parse_args()
    report = run(args.state, args.specstory.resolve(), args.entire.resolve())
    print(json.dumps({key: value for key, value in report.items() if key != 'commands'}, indent=2))


if __name__ == '__main__': main()
