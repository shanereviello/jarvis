"""Authenticated private n8n-to-Codex runtime API; no public ingress or OAuth."""
import argparse
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import pwd
import threading


def local():
    spec = importlib.util.spec_from_file_location('codex_private_runtime', Path(__file__).with_name('codex_runtime.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module


def server(runtime, token, address=('127.0.0.1', 8766)):
    if type(token) is not bytes or not 32 <= len(token) <= 256 or not all(33 <= b <= 126 for b in token):
        raise ValueError('private bounded bridge credential required')
    m = local()
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def log_message(self, *args): pass

        def reply(self, status, value):
            raw = m.encoded(value)
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers(); self.wfile.write(raw)

        def allowed(self):
            supplied = self.headers.get('Authorization', '').encode('utf-8')
            if not hmac.compare_digest(supplied, b'Bearer ' + token):
                self.close_connection = True
                self.reply(403, dict(error='runtime access refused'))
                return False
            self.connection.settimeout(5)
            return True

        def do_GET(self):
            if not self.allowed(): return
            try:
                if not self.path.startswith('/v1/runs/'): raise ValueError('unknown route')
                result = runtime.status(self.path[len('/v1/runs/'):])
                self.reply(200, result)
            except (ValueError, OSError): self.reply(409, dict(error='runtime request refused; retain dispatch identity'))

        def do_POST(self):
            if not self.allowed(): return
            try:
                if self.headers.get('Transfer-Encoding'): raise ValueError('fixed bounded body required')
                if self.headers.get('Content-Type') != 'application/json': raise ValueError('JSON required')
                length = int(self.headers.get('Content-Length', '-1'))
                if not 1 <= length <= 128 * 1024: raise ValueError('bounded body required')
                raw = self.rfile.read(length)
                if len(raw) != length: raise ValueError('truncated request')
                def pairs(items):
                    result = {}
                    for key,value in items:
                        if key in result: raise ValueError('duplicate JSON key')
                        result[key] = value
                    return result
                value = json.loads(raw, object_pairs_hook=pairs,
                    parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
                if self.path == '/v1/dispatch':
                    self.reply(202, runtime.dispatch(value))
                elif self.path == '/v1/interrupt' and type(value) is dict and set(value) == {'dispatch_id'}:
                    self.reply(200, runtime.interrupt(value['dispatch_id']))
                else: raise ValueError('unknown route')
            except (ValueError, TypeError, KeyError, OSError, RecursionError) as error:
                self.close_connection = True
                if getattr(error,'code',None)=='execution_not_authorized_before_dispatch':
                    self.reply(403,dict(contract='codex-admission-refusal.v1',dispatch=value['dispatch_id'],state='failed',reason='execution_not_authorized'))
                else:self.reply(409, dict(error='runtime request refused or uncertain; retain dispatch identity'))
    return ThreadingHTTPServer(address, Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--policy', type=Path, required=True)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--bridge-token-file', type=Path, required=True)
    parser.add_argument('--reporting-policy',type=Path)
    parser.add_argument('--checkpoint-python',type=Path)
    parser.add_argument('--native-socket',type=Path,required=True)
    parser.add_argument('--native-peer-uid',type=int,required=True)
    native_identity=parser.add_mutually_exclusive_group(required=True)
    native_identity.add_argument('--native-uid',type=int)
    native_identity.add_argument('--native-user')
    parser.add_argument('--checkpoint-socket',type=Path,required=True)
    parser.add_argument('--initialize', action='store_true')
    parser.add_argument('--bind', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8766)
    args = parser.parse_args(); m = local()
    if args.native_user:
        if (not args.native_user.isascii() or not args.native_user[0].isalpha() or
                not args.native_user.replace('_','').replace('-','').isalnum()):
            raise ValueError('exact named native service identity required')
        args.native_uid=pwd.getpwnam(args.native_user).pw_uid
    m.history_unix().uid(args.native_uid)
    if args.native_uid==os.getuid():raise ValueError('native coder and private adapter need distinct identities')
    spec=importlib.util.spec_from_file_location('private_runtime_protected_config',Path(__file__).with_name('protected_config.py'))
    protected=importlib.util.module_from_spec(spec);spec.loader.exec_module(protected)
    selected=protected.decode(args.policy)
    if args.initialize:
        # Initialization creates no native process, HTTP listener or model turn.
        runtime=m.Runtime(args.state,selected,create=True)
        runtime.close()
        print(json.dumps(dict(initialized=True,models_started=0,listener_started=False)))
        return
    token=protected.read(args.bridge_token_file,maximum=257).strip()
    reporter=None
    if args.reporting_policy:
        spec=importlib.util.spec_from_file_location('private_runtime_reporting',Path(__file__).with_name('runtime_reporting.py'))
        reporting=importlib.util.module_from_spec(spec);spec.loader.exec_module(reporting)
        reporter=reporting.Reporter(protected.decode(args.reporting_policy),selected)
    checkpoint=None
    if args.checkpoint_python:
        if reporter is None:raise ValueError('checkpoint tool requires installed reporting policy')
        spec=importlib.util.spec_from_file_location('private_runtime_checkpoint',Path(__file__).with_name('runtime_checkpoint_mcp.py'))
        tool=importlib.util.module_from_spec(spec);spec.loader.exec_module(tool)
        checkpoint=tool.BrokerLaunch(args.checkpoint_socket,os.getuid(),args.checkpoint_python,handoff='handoff' in reporter.configuration)
    if reporter is None or checkpoint is None:raise ValueError('installed automatic reporting and scoped recorder required')
    if set(reporter.task_contexts)!=set(selected['issues']) or reporter.configuration['capture'] is None:
        raise ValueError('exact retained task contracts and selected capture installation required')
    if (not {'source_socket','source_peer_uid'}<=set(reporter.configuration['capture']) or
            str(args.native_socket)==reporter.configuration['capture']['source_socket']):
        raise ValueError('separate credential-free native source reader required')
    runtime = m.Runtime(args.state, selected,reporter=reporter,checkpoint_tool=checkpoint,
        client_factory=lambda executable,cwd:m.SocketAppServer(args.native_socket,args.native_peer_uid))
    http = server(runtime, token, (args.bind, args.port))
    spec=importlib.util.spec_from_file_location('private_runtime_checkpoint_broker',Path(__file__).with_name('runtime_checkpoint_broker.py'))
    broker_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(broker_module)
    stopped=threading.Event()
    os.environ.clear();os.environ.update(PATH='/usr/bin:/bin',HOME='/nonexistent',LANG='C.UTF-8')
    try:
        with broker_module.Server(args.checkpoint_socket,runtime,reporter.configuration,args.native_uid,
                on_bound=lambda path:broker_module.acl_on_bound(path,args.native_uid)) as broker:
            def serve_checkpoints():
                while not stopped.is_set():broker.serve_once()
            thread=threading.Thread(target=serve_checkpoints,daemon=True);thread.start()
            try:http.serve_forever()
            finally:stopped.set();thread.join(timeout=3)
    finally:http.server_close();runtime.close()


if __name__ == '__main__':
    try:main()
    except Exception:raise SystemExit('Private Codex runtime entry refused; retain installed configuration and journal.') from None
