"""Accept the sandbox proof producer with temporary, inactive systemd units."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import uuid


def local(name):
    spec = importlib.util.spec_from_file_location('sandbox_host_' + name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def main():
    if os.getuid() != 0 or os.geteuid() != 0:raise ValueError('root required')
    issue = str(uuid.uuid4());workspace = '/srv/rras-sandbox-proof-fixture-' + issue
    release = '/opt/rras-engineering/releases/standardized-history-9e7954c07fdb'
    binary = Path(release) / 'runtime/bin/codex'
    if hashlib.sha256(binary.read_bytes()).hexdigest() != 'd2752c52353401f7f6efbfcea68796f4f7a3d3e4769f5d1da53fa49d4856b72f':
        raise ValueError('installed fixture binary differs')
    units = local('codex_issue_units').render(issue,workspace,release)
    directory = Path('/etc/systemd/system')
    audit = Path('/run') / ('rras-sandbox-proof-fixture-' + issue)
    created = [];audit_created = False
    def systemctl(*args):
        subprocess.run(['/usr/bin/systemctl',*args],capture_output=True,check=True,timeout=30)
    try:
        audit.mkdir(mode=0o700);audit_created = True
        for name, body in ((units['service_name'],units['service']), (units['socket_name'],units['listener'])):
            path = directory / name;raw = body.encode()
            fd = os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o644)
            created.append((path,hashlib.sha256(raw).hexdigest()))
            with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
        systemctl('daemon-reload')
        config = dict(unit_directory=str(directory),native_release=release,proof_directory=str(audit),proof_name='fixture.proof',
            request=dict(issue_id=issue,workspace=workspace,native_socket=units['socket_path']))
        result = local('onboarding_sandbox_producer').produce(config)
        proof = json.loads((audit/'fixture.proof').read_text())
        keys = ('issue_id','workspace','socket','service_name','socket_name','service_sha256','socket_sha256','native_release','native_binary_sha256')
        expected = {key:proof[key] for key in keys}
        if not local('onboarding_sandbox_proof').Verifier(audit/'fixture.proof')(expected) or result['models_started'] != 0:
            raise ValueError('retained proof did not independently verify')
        print(json.dumps(dict(temporary_units_verified=True, native_sandbox_proof_retained_and_verified=True,
            production_services_changed=False, models_started=0),sort_keys=True))
    finally:
        for path, expected in reversed(created):
            if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise ValueError('temporary unit changed; retain for inspection')
            path.unlink()
        if created:systemctl('daemon-reload')
        if audit_created:
            for path in audit.iterdir():
                if path.name != 'fixture.proof' or path.is_symlink() or not path.is_file():
                    raise ValueError('unexpected fixture file; retain for inspection')
                path.unlink()
            audit.rmdir()


if __name__ == '__main__':main()
