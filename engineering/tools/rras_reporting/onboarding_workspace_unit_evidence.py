"""Verify exact root-installed per-issue units and independent sandbox proof.

Unit-file equality alone cannot prove effective systemd or sandbox isolation;
the protected caller supplies a fresh independent runtime verifier. This
module never creates or starts a unit.
"""
import hashlib
import importlib.util
import os
from pathlib import Path
import stat


def local(name):
    spec = importlib.util.spec_from_file_location('workspace_units_' + name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


class Verifier:
    def __init__(self, unit_dir, native_release, verify_runtime, *, owner=0):
        self.directory, self.release, self.owner = Path(unit_dir), native_release, owner
        if (not self.directory.is_absolute() or self.directory.resolve() != self.directory or
                not callable(verify_runtime) or type(owner) is not int or owner < 0):
            raise ValueError('protected unit directory and runtime verifier required')
        self.verify_runtime = verify_runtime

    def read(self, path):
        directory = self.directory.lstat()
        if not stat.S_ISDIR(directory.st_mode) or directory.st_uid != self.owner or directory.st_mode & 0o022:
            raise ValueError('protected unit directory required')
        for parent in self.directory.parents:
            ancestor = parent.lstat()
            if (not stat.S_ISDIR(ancestor.st_mode) or ancestor.st_uid not in (0,self.owner) or
                    (ancestor.st_mode & 0o022 and not (ancestor.st_uid == 0 and ancestor.st_mode & stat.S_ISVTX))):
                raise ValueError('protected unit ancestry required')
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != self.owner or info.st_nlink != 1 or
                stat.S_IMODE(info.st_mode) not in (0o600,0o640,0o644) or info.st_size > 65536):
            raise ValueError('protected regular unit file required')
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            opened = os.fstat(fd)
            if (opened.st_dev,opened.st_ino,opened.st_mode,opened.st_size) != (info.st_dev,info.st_ino,info.st_mode,info.st_size):
                raise ValueError('unit changed during verification')
            with os.fdopen(fd,'rb',closefd=False) as stream:return stream.read(65537)
        finally:os.close(fd)

    def __call__(self, request):
        units = local('codex_issue_units').render(request['issue_id'], request['workspace'], self.release)
        if request['native_socket'] != units['socket_path']:
            raise ValueError('issue socket differs from protected unit')
        service = self.read(self.directory / units['service_name'])
        listener = self.read(self.directory / units['socket_name'])
        if service != units['service'].encode() or listener != units['listener'].encode():
            raise ValueError('installed issue units differ from protected template')
        expected = dict(issue_id=request['issue_id'], workspace=request['workspace'], socket=units['socket_path'],
            service_name=units['service_name'], socket_name=units['socket_name'],
            service_sha256=hashlib.sha256(service).hexdigest(), socket_sha256=hashlib.sha256(listener).hexdigest(),
            native_release=self.release)
        if self.verify_runtime(expected) is not True:
            raise ValueError('current effective unit and sandbox isolation unverified')
        return True
