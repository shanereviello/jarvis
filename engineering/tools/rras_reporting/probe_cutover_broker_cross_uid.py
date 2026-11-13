"""Test root broker transport with distinct temporary UIDs in an offline container."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
IMAGE = 'sha256:b99f4564d5e17ec0183314c0d2f6f633657cff4916fad0f05f6e7667722da432'
BASE = Path('/tmp/rras-cutover-broker-probe')
PEER, ROGUE = 61183, 61184


def local(name):
    spec = importlib.util.spec_from_file_location('cutover_probe_' + name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def accept(server, listener, broker):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if server.serve_once(listener, broker):return True
    return False


def inside():
    if not Path('/.dockerenv').exists() or os.getuid() != 0:
        raise ValueError('isolated root container required')
    devices = {line.split(':', 1)[0].strip() for line in Path('/proc/self/net/dev').read_text().splitlines() if ':' in line}
    if devices != {'lo'}:
        raise ValueError('network-isolated fixture required')
    BASE.mkdir(mode=0o750)
    os.chown(BASE, 0, PEER)
    path = BASE / 'broker.sock'
    class Broker:
        peer_uid = PEER
        def call(self, peer, operation):
            if peer != PEER or operation != 'digest':
                raise ValueError('fixture access refused')
            return 'a' * 64
    server = local('codex_cutover_broker_server')
    def child(uid):
        pid = os.fork()
        if pid == 0:
            try:
                os.setgroups([]);os.setgid(PEER);os.setuid(uid)
                value = local('codex_cutover_broker_transport').call(str(path), 'digest')
                os._exit(0 if value == 'a' * 64 else 2)
            except BaseException:
                os._exit(3)
        return pid
    with server.listener(path, PEER) as listener:
        broker = Broker()
        good = child(PEER)
        if not accept(server, listener, broker) or os.waitpid(good, 0)[1] != 0:
            raise ValueError('expected peer was refused')
        rogue = child(ROGUE)
        if not accept(server, listener, broker) or os.waitpid(rogue, 0)[1] == 0:
            raise ValueError('same-group rogue peer was accepted')
    if path.exists():
        raise ValueError('listener socket was not cleaned')
    print(json.dumps(dict(root_broker_peer_verified=True, distinct_numeric_uids=True,
        same_group_rogue_denied=True, socket_cleaned=True, network_isolated=True,
        production_changed=False, models_started=0), sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inside', action='store_true')
    parser.add_argument('--isolated-containers', action='store_true')
    args = parser.parse_args()
    if args.inside:
        inside();return
    if not args.isolated_containers:
        parser.error('explicit isolated fixture required')
    name = 'rras-cutover-probe-' + uuid.uuid4().hex[:10]
    command = ['docker', 'run', '--rm', '--name', name, '--pull=never', '--network', 'none', '--read-only',
        '--cap-drop', 'ALL', '--cap-add', 'SETUID', '--cap-add', 'SETGID', '--cap-add', 'CHOWN',
        '--security-opt', 'no-new-privileges:true', '--tmpfs', '/tmp:rw,nosuid,nodev,size=32m,mode=1777',
        '--mount', 'type=bind,source=' + str(ROOT) + ',target=/fixture/engineering,readonly',
        '--user', '0:0', '--entrypoint', '/usr/bin/env', IMAGE, '-i', 'PATH=/usr/bin:/bin',
        'HOME=/nonexistent', 'LANG=C.UTF-8', '/opt/hermes/.venv/bin/python', '-I', '-B',
        '/fixture/engineering/tools/rras_reporting/probe_cutover_broker_cross_uid.py', '--inside']
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=45)
        if result.returncode:
            raise ValueError('offline broker fixture failed: ' + result.stderr[-2000:])
        print(result.stdout.strip())
    finally:
        subprocess.run(['docker', 'rm', '-f', name], capture_output=True, timeout=15)


if __name__ == '__main__':
    main()
