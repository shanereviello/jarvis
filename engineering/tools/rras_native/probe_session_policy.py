"""Exercise pinned native session routing without launching Codex or inference.

Run with the reviewed Hermes dependency environment and an empty environment.
Synthetic server requests test the real handler, not a copied RRAS policy.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

SESSION_SHA = '6788277acd880a900faaedfdf948caca5bcad7f33e8fa2db3815cd47b7d7c651'


def probe(source, output):
    source, output = Path(source).resolve(strict=True), Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError('evidence destination must be absent')
    session_file = source / 'agent/transports/codex_app_server_session.py'
    if hashlib.sha256(session_file.read_bytes()).hexdigest() != SESSION_SHA:
        raise ValueError('session source pin changed')
    sys.path.insert(0, str(source))
    from agent.transports.codex_app_server_session import CodexAppServerSession

    class Recorder:
        def initialize(self, **kwargs):
            self.initialized = kwargs

        def request(self, method, params, **kwargs):
            self.started = (method, params)
            return {'thread': {'id': 'synthetic-thread'}}

        def respond(self, rid, result):
            self.reply = result

        def respond_error(self, rid, **error):
            self.reply = error

    cases = []
    recorder = Recorder()
    session = CodexAppServerSession(cwd=str(source))
    session._client = recorder
    session.ensure_started()
    cases.append({'name': 'native_thread_start_no_injected_tools',
                  'passed': recorder.started == ('thread/start', {'cwd': str(source)})})
    for method, params, expected in (
        ('item/commandExecution/requestApproval', {'command': 'benign-fixture'}, {'decision': 'decline'}),
        ('item/fileChange/requestApproval', {'grantRoot': '/fixture'}, {'decision': 'decline'}),
        ('item/permissions/requestApproval', {}, {'decision': 'decline'}),
        ('mcpServer/elicitation/request', {'serverName': 'foreign'}, {'action': 'decline', 'content': None, '_meta': None}),
        ('mcpServer/elicitation/request', {'serverName': 'hermes-tools'}, {'action': 'accept', 'content': None, '_meta': None}),
    ):
        session._handle_server_request({'id': 1, 'method': method, 'params': params})
        cases.append({'name': method + ':' + params.get('serverName', 'default'),
                      'passed': recorder.reply == expected, 'response': recorder.reply})
    session._handle_server_request({'id': 2, 'method': 'unknown/fixture', 'params': {}})
    cases.append({'name': 'unknown_request_rejected', 'passed': recorder.reply['code'] == -32601})
    for choice in ('deny', 'timeout', 'unexpected', 'once'):
        session._approval_callback = lambda *args, _choice=choice, **kwargs: _choice
        expected = 'accept' if choice == 'once' else 'decline'
        for method in ('_decide_exec_approval', '_decide_apply_patch_approval'):
            cases.append({'name': method + ':' + choice,
                          'passed': getattr(session, method)({}) == expected})
    def broken(*args, **kwargs):
        raise RuntimeError('synthetic callback failure')
    session._approval_callback = broken
    for method in ('_decide_exec_approval', '_decide_apply_patch_approval'):
        cases.append({'name': method + ':callback_exception',
                      'passed': getattr(session, method)({}) == 'decline'})
    result = {'scope': 'native-handler-synthetic-requests', 'source_sha256': SESSION_SHA,
              'api_calls': 0, 'live_session_tested': False,
              'hermes_tools_elicitation_autoaccepted': True,
              'cases': cases, 'success': all(c['passed'] for c in cases)}
    with output.open('x') as stream:
        import os
        os.chmod(output, 0o600)
        json.dump(result, stream, indent=2)
        stream.write('\n')
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', required=True)
    p.add_argument('--evidence', required=True)
    args = p.parse_args()
    result = probe(args.source, args.evidence)
    print(json.dumps(result))
    raise SystemExit(0 if result['success'] else 1)
