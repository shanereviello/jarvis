"""Authenticated private n8n-to-Codex runtime API; no public ingress or OAuth."""
import argparse
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path


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
            except (ValueError, TypeError, KeyError, OSError, RecursionError):
                self.close_connection = True
                self.reply(409, dict(error='runtime request refused or uncertain; retain dispatch identity'))
    return ThreadingHTTPServer(address, Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--policy', type=Path, required=True)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--bridge-token-file', type=Path, required=True)
    parser.add_argument('--reporting-policy',type=Path)
    parser.add_argument('--checkpoint-python',type=Path)
    parser.add_argument('--codex-home',type=Path,required=True)
    parser.add_argument('--initialize', action='store_true')
    parser.add_argument('--bind', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8766)
    args = parser.parse_args(); m = local()
    if args.codex_home!=args.state/'codex-home':raise ValueError('dedicated runtime-owned Codex home required')
    selected = json.loads(m.private(args.policy).read_bytes())
    if args.initialize:
        # Initialization creates no native process, HTTP listener or model turn.
        runtime=m.Runtime(args.state,selected,create=True)
        try:args.codex_home.mkdir(mode=0o700)
        finally:runtime.close()
        print(json.dumps(dict(initialized=True,models_started=0,listener_started=False)))
        return
    # Separate native integration home: no inherited personal MCP/OAuth config.
    home=m.private(args.codex_home,True)
    token = m.private(args.bridge_token_file).read_bytes().strip()
    reporter=None
    if args.reporting_policy:
        spec=importlib.util.spec_from_file_location('private_runtime_reporting',Path(__file__).with_name('runtime_reporting.py'))
        reporting=importlib.util.module_from_spec(spec);spec.loader.exec_module(reporting)
        reporter=reporting.Reporter(json.loads(m.private(args.reporting_policy).read_bytes()),selected)
    checkpoint=None
    if args.checkpoint_python:
        if reporter is None:raise ValueError('checkpoint tool requires installed reporting policy')
        spec=importlib.util.spec_from_file_location('private_runtime_checkpoint',Path(__file__).with_name('runtime_checkpoint_mcp.py'))
        tool=importlib.util.module_from_spec(spec);spec.loader.exec_module(tool)
        checkpoint=tool.Launch(args.state,args.reporting_policy,args.checkpoint_python)
    runtime = m.Runtime(args.state, selected,reporter=reporter,checkpoint_tool=checkpoint,
        client_factory=lambda executable,cwd:m.AppServer(executable,cwd,codex_home=home))
    http = server(runtime, token, (args.bind, args.port))
    try: http.serve_forever()
    finally: http.server_close(); runtime.close()


if __name__ == '__main__': main()
