"""Host a single fixed cutover while excluding runtime restarts.

This composition is not an installed entry point. Its caller must provide
protected transition state and independently implemented read-only verifiers.
"""
from contextlib import contextmanager
import fcntl
import importlib.util
import os
from pathlib import Path
import stat
import time


def local(name):
    spec = importlib.util.spec_from_file_location('cutover_root_host_' + name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def lock(directory):
    directory = local('codex_cutover_files').private_directory(directory, 0)
    if os.getuid() != 0 or os.geteuid() != 0:
        raise ValueError('root host required')
    fd = os.open(directory / 'admission.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError('root-private lock required')
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)


def run(*, unit, socket_path, peer_uid, peer_gid, policy_path, audit_dir, transition,
        verify_journal, verify_evidence, timeout_seconds=300):
    if (not callable(verify_journal) or not callable(verify_evidence) or
            type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 900):
        raise ValueError('bounded host and independent verifiers required')
    with lock(audit_dir):
        guard = local('codex_cutover_persistent_guard').Guard(unit, audit_dir)
        # Failure after this point intentionally leaves the runtime mask in place.
        guard.acquire()
        files = local('codex_cutover_root_files').Files(policy_path, audit_dir)
        broker = local('codex_cutover_fixed_broker').Broker(peer_uid=peer_uid, transition=transition,
            files=files, verify_stopped=guard.verified, verify_journal=verify_journal, verify_evidence=verify_evidence)
        server = local('codex_cutover_broker_server')
        with server.listener(socket_path, peer_gid) as listener:
            deadline = time.monotonic() + timeout_seconds
            while broker.stage != 'complete':
                if time.monotonic() >= deadline:
                    raise TimeoutError('cutover timed out; retained state and runtime mask require inspection')
                server.serve_once(listener, broker)
        guard.release(lambda: files.digest() == broker.new and verify_journal(broker.new, broker.plan_sha) is True)
        return dict(completed=True, runtime_started=False, models_started=0, plan_sha256=broker.plan_sha)
