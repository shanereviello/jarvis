"""Durable file primitives for an offline policy cutover.

Callers must separately hold the protected admission and runtime locks. These
primitives do not verify history, authorize spending, or control a service.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import stat


def local(name):
    spec = importlib.util.spec_from_file_location('cutover_files_' + name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def private_directory(path, owner):
    path = Path(path)
    if not path.is_absolute() or path.resolve() != path:
        raise ValueError('absolute nonsymlink directory required')
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != owner or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError('private owner-controlled directory required')
    for parent in path.parents:
        value = parent.lstat()
        if not stat.S_ISDIR(value.st_mode) or value.st_uid not in (0, owner):
            raise ValueError('protected directory ancestry required')
        if value.st_mode & 0o022 and not (value.st_uid == 0 and value.st_mode & stat.S_ISVTX):
            raise ValueError('writable directory ancestry forbidden')
    return path


def directory_sync(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def retain(directory, name, value, *, owner=0):
    """Create one private, immutable-by-convention record; never overwrite."""
    directory = private_directory(directory, owner)
    if os.geteuid() != owner or not re.fullmatch(r'[a-z0-9][a-z0-9.-]{0,127}', name):
        raise ValueError('invalid record owner or name')
    raw = local('codex_runtime').encoded(value)
    if len(raw) > 8 * 1024 * 1024:
        raise ValueError('record too large')
    fd = os.open(directory / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        with os.fdopen(fd, 'wb', closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(fd)
    finally:
        os.close(fd)
    directory_sync(directory)
    return hashlib.sha256(raw).hexdigest()


def install(policy_path, expected_old_sha256, candidate, *, owner=0):
    """Replace a protected policy only if its canonical old digest still matches."""
    if os.geteuid() != owner:
        raise ValueError('policy owner required')
    path = Path(policy_path)
    protected = local('protected_config')
    runtime = local('codex_runtime')
    raw = protected.read(path, maximum=8 * 1024 * 1024, require_root=(owner == 0))
    original = path.lstat()
    if original.st_uid != owner:
        raise ValueError('unexpected policy owner')
    old = runtime.policy(json.loads(raw))
    new = runtime.policy(candidate)
    if hashlib.sha256(runtime.encoded(old)).hexdigest() != expected_old_sha256:
        raise ValueError('installed policy changed')
    encoded = runtime.encoded(new)
    temp = path.parent / ('.' + path.name + '.' + secrets.token_hex(16) + '.tmp')
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        os.fchown(fd, original.st_uid, original.st_gid)
        os.fchmod(fd, stat.S_IMODE(original.st_mode))
        with os.fdopen(fd, 'wb', closefd=False) as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(fd)
        # A held admission lock protects cooperating writers; also detect an
        # unexpected file replacement before publishing the candidate.
        current = path.lstat()
        if (current.st_dev, current.st_ino, current.st_mtime_ns, current.st_size) != (
                original.st_dev, original.st_ino, original.st_mtime_ns, original.st_size):
            raise ValueError('installed policy changed during cutover')
        os.replace(temp, path)
        directory_sync(path.parent)
    finally:
        os.close(fd)
        try:
            temp.unlink()
        except FileNotFoundError:
            pass
    return hashlib.sha256(encoded).hexdigest()
