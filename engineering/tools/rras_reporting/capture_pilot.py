"""Explicit single-session pilot in isolated HOME/Git; no collector installation.

Requires separate operator authorization for real input. Source transcript and
outputs stay private; console output contains only coverage/digest metadata.
Use the network-restricted execution environment. No inference or remote Git.
"""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import uuid

PINS = {'specstory': '25b8a1b7c13b6cccd514845608785057b980ad3d55029d75527a0d9aaf0603c4',
        'entire': '2b480571db74a57979422796f5697e733de24019dbc13765980e689ddaac7245'}
MAX_SOURCE = 128 * 1024 * 1024


def selected_source(path, session):
    if type(session) is not str or str(uuid.UUID(session)) != session: raise ValueError('exact session UUID required')
    path = Path(path)
    if not path.is_absolute() or path.resolve(strict=True) != path: raise ValueError('canonical source required')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        # The native app's file mode is not our custody policy: this installation
        # writes group-readable/group-writable sessions. Read them as untrusted
        # evidence, never chmod them or infer authority from their owner/content.
        # All copies/exports are placed in newly created private custody below.
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1 or
                info.st_mode & 0o002 or not 1 <= info.st_size <= MAX_SOURCE):
            raise ValueError('bounded caller-owned, non-world-writable source required')
        raw = stream.read(info.st_size)
    # Snapshot the initial complete-line prefix; appends may continue in the app.
    raw = raw[:raw.rfind(b'\n') + 1]
    rows = [json.loads(line) for line in raw.splitlines()]
    meta = [x['payload'] for x in rows if x.get('type') == 'session_meta']
    if len(meta) != 1 or meta[0].get('id') != session:
        raise ValueError('source does not match the explicitly authorized session')
    return raw, rows


def visible(rows):
    messages = []
    for row in rows:
        if row.get('type') != 'event_msg': continue
        payload = row.get('payload', {})
        if payload.get('type') in ('user_message', 'agent_message'):
            text = payload.get('message')
            if type(text) is str and text.strip(): messages.append(text.strip())
        elif payload.get('type') == 'item_completed':
            item = payload.get('item', {})
            if item.get('type') in ('UserMessage', 'AgentMessage'):
                text = '\n'.join(part['text'] for part in item.get('content', [])
                                 if part.get('type') == 'text' and type(part.get('text')) is str)
                if text.strip(): messages.append(text.strip())
    return messages


def response_coverage(rows, export):
    """Check visible response-message text too; UI fixtures alone can undercount.

    Only aggregate counts leave private custody. Reasoning records and analysis
    channels are excluded. Text inclusion is a coverage probe, not proof of actor
    authentication or complete tool/media/source capture.
    """
    found, matched, omitted_context = Counter(), Counter(), Counter()
    unmatched = 0
    for row in rows:
        payload = row.get('payload', {})
        if (row.get('type') != 'response_item' or payload.get('type') != 'message' or
                payload.get('role') not in ('user', 'assistant')): continue
        phase = payload.get('phase', payload.get('channel', 'unspecified'))
        if phase in ('analysis', 'reasoning'): continue
        key = payload['role'] + ':' + (phase if phase in ('commentary', 'final_answer', 'final', 'unspecified') else 'other')
        texts = [part['text'].strip() for part in payload.get('content', []) if
                 part.get('type') in ('input_text', 'output_text') and type(part.get('text')) is str and part['text'].strip()]
        if not texts: continue
        found[key] += 1
        if all(text in export for text in texts): matched[key] += 1
        elif payload['role'] == 'user' and all(text.startswith('<external_codex_apps_open_page>') for text in texts):
            omitted_context['app_navigation'] += 1
        elif payload['role'] == 'user' and all(text.startswith('<environment_context>') for text in texts):
            omitted_context['environment_context'] += 1
        else: unmatched += 1
    return dict(method='full text inclusion; no independent attribution or full tool/media completeness claim',
        source_message_counts=dict(found), matched_message_counts=dict(matched),
        omitted_context_records=dict(omitted_context), unmatched_visible_or_unknown_messages=unmatched)


def write(path, raw):
    with path.open('xb') as stream:
        os.fchmod(stream.fileno(), 0o600); stream.write(raw); stream.flush(); os.fsync(stream.fileno())


def run(root, source, session, specstory, entire, authorization_reference):
    if type(authorization_reference) is not str or not authorization_reference.strip() or len(authorization_reference) > 2048:
        raise ValueError('explicit pilot authorization reference required')
    root = Path(root)
    if not root.is_absolute() or root.resolve(strict=False) != root: raise ValueError('canonical new private state required')
    for name, binary in [('specstory', specstory), ('entire', entire)]:
        if hashlib.sha256(Path(binary).read_bytes()).hexdigest() != PINS[name]: raise ValueError('reviewed collector binary required')
    raw, rows = selected_source(source, session)
    root.mkdir(mode=0o700, exist_ok=False)
    home, repo = root / 'isolated-home', root / 'isolated-repo'
    home.mkdir(mode=0o700); repo.mkdir(mode=0o700)
    sessions = home / '.codex/sessions/2026/11/07'; sessions.mkdir(parents=True, mode=0o700)
    transcript = sessions / ('rollout-2026-11-07T00-00-00-' + session + '.jsonl')
    write(root / 'exact-source-snapshot.jsonl', raw)
    # SpecStory discovery filters by working directory even with an explicit ID.
    # Keep exact source bytes separately; relocate only session_meta.cwd in the
    # collector copy so neither tool needs to operate in a real checkout.
    relocated = []
    for line in raw.splitlines(keepends=True):
        row = json.loads(line)
        if row.get('type') == 'session_meta':
            row['payload']['cwd'] = str(repo)
            line = (json.dumps(row, ensure_ascii=False) + '\n').encode()
        relocated.append(line)
    collector_raw = b''.join(relocated)
    write(transcript, collector_raw)
    env = dict(HOME=str(home), PATH=str(Path(entire).parent) + ':/usr/bin:/bin',
               LANG='C.UTF-8', CI='1', DO_NOT_TRACK='1')
    commands = []
    def command(argv, data=None):
        result = subprocess.run([str(x) for x in argv], input=data, cwd=repo, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45, check=False,
                                umask=0o077)
        commands.append(dict(index=len(commands) + 1, operation=str(argv[0]).split('/')[-1], exit_code=result.returncode))
        # Exact private output retained; neither transcript nor errors echo to chat.
        write(root / ('command-%02d.stdout' % len(commands)), result.stdout)
        write(root / ('command-%02d.stderr' % len(commands)), result.stderr)
        return result
    for args in [('init', '-q'), ('config', 'user.name', 'Isolated Capture Pilot'),
                 ('config', 'user.email', 'synthetic@example.invalid'),
                 ('commit', '--allow-empty', '-qm', 'Isolated capture baseline')]:
        if command(['git', *args]).returncode: raise ValueError('isolated Git initialization failed; retain state')
    flags = ['--no-cloud-sync', '--no-usage-analytics', '--no-version-check', '--no-telemetry-prompts', '--no-stats']
    first = command([specstory, 'sync', 'codex', *flags, '--print', '-s', session])
    second = command([specstory, 'sync', 'codex', *flags, '--print', '-s', session])
    export = first.stdout.decode('utf-8')
    expected = visible(rows)
    # Secret filtering/normalization may change exact text. Report coverage instead
    # of treating a zero exit or nonempty Markdown as proof of complete capture.
    matched = sum(text in export for text in expected)
    enable = command([entire, 'enable', '--agent', 'codex', '--local', '--skip-push-sessions', '--telemetry=false', '--yes'])
    if enable.returncode: raise ValueError('isolated Entire setup failed; retain private output')
    settings = json.loads((repo / '.entire/settings.local.json').read_bytes())
    if settings.get('strategy_options', {}).get('push_sessions') is not False or settings.get('telemetry') is not False:
        raise ValueError('private Entire settings differ; do not run hooks')
    hooks = []
    for verb, event in [('session-start', 'SessionStart'), ('user-prompt-submit', 'UserPromptSubmit'),
                        ('stop', 'Stop'), ('session-end', 'SessionEnd')]:
        payload = dict(session_id=session, transcript_path=str(transcript), cwd=str(repo), hook_event_name=event,
            source='startup', prompt='Authorized isolated transcript replay; no new turn.',
            last_assistant_message='No new model output.', reason='other')
        result = command([entire, 'hooks', 'codex', verb], json.dumps(payload).encode())
        hooks.append(dict(event=event, exit_code=result.returncode))
    inventory = command([entire, 'session', 'list', '--json'])
    tracked = json.loads(inventory.stdout) if inventory.returncode == 0 else []
    refs = command(['git', 'for-each-ref', 'refs/entire', '--format=%(refname)']).stdout.decode().splitlines()
    report = dict(contract='reporting-capture-pilot.v1', session_id=session,
        authorization_reference=authorization_reference, snapshot_sha256=hashlib.sha256(raw).hexdigest(),
        snapshot_bytes=len(raw), snapshot_records=len(rows), executable_sha256=PINS,
        supplied_provider_credentials=False, paid_model_calls=0, real_repository_hooks_changed=False,
        source_access='read-only complete-line prefix; source-native appends may continue',
        exact_source_snapshot_retained=(root / 'exact-source-snapshot.jsonl').read_bytes() == raw,
        isolated_collector_copy_unchanged=transcript.read_bytes() == collector_raw,
        session_meta_cwd_relocated_for_isolation=True,
        specstory=dict(exit_code=first.returncode, repeat_exit_code=second.returncode,
            nonempty_export=bool(export.strip()), repeated_output_identical=first.stdout == second.stdout,
            ui_messages_found=len(expected), ui_messages_exactly_present=matched,
            normalized_or_redacted_or_missing=len(expected) - matched,
            redaction='collector default enabled; no universal secret-filtering guarantee',
            response_coverage=response_coverage(rows, export)),
        entire=dict(hooks=hooks, session_tracked=any(x.get('session_id') == session for x in tracked),
                    persistent_refs_without_code_commit=refs),
        network_boundary='run in restricted sandbox; uploads/analytics disabled; no packet audit claimed',
        limitations=['One explicitly authorized source snapshot; working directory relocated only in collector copy.',
                     'Does not establish discovery in real working directories or all session branches/machines.',
                     'Hook replay in isolated Git; no live inference, worker teardown, rotation or handoff demonstrated.'],
        commands=commands)
    write(root / 'result.json', (json.dumps(report, sort_keys=True, indent=2) + '\n').encode())
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ['state', 'source-transcript', 'specstory', 'entire']:
        parser.add_argument('--' + flag, type=Path, required=True)
    parser.add_argument('--session-id', required=True)
    parser.add_argument('--authorization-reference', required=True)
    args = parser.parse_args()
    try:
        report = run(args.state, args.source_transcript, args.session_id, args.specstory.resolve(), args.entire.resolve(), args.authorization_reference)
        print(json.dumps({k: v for k, v in report.items() if k not in ('commands', 'authorization_reference')}, sort_keys=True))
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError):
        parser.exit(1, 'Capture pilot refused or incomplete; retain private state and inspect locally.\n')


if __name__ == '__main__': main()
