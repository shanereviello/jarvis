"""Check selected effective systemd properties plus independent sandbox proof.

This reader cannot install units or launch models. The sandbox verifier must
independently bind a current probe to these exact service and socket hashes.
"""
from pathlib import Path
import subprocess


class Verifier:
    def __init__(self, unit_dir, verify_sandbox, *, run=subprocess.run):
        self.directory = Path(unit_dir)
        if not self.directory.is_absolute() or self.directory.resolve() != self.directory or not callable(verify_sandbox):
            raise ValueError('protected unit directory and sandbox verifier required')
        self.verify_sandbox, self.run = verify_sandbox, run

    def properties(self, unit, names):
        command = ['/usr/bin/systemctl','show',unit,'--no-pager'] + ['--property='+name for name in names]
        result = self.run(command, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=15)
        if result.returncode != 0 or len(result.stdout.encode()) > 65536:
            raise ValueError('effective unit properties unavailable')
        values = {}
        for line in result.stdout.splitlines():
            key, sep, value = line.partition('=')
            if not sep or key not in names or key in values:
                raise ValueError('unexpected effective unit properties')
            values[key] = value
        if set(values) != set(names):raise ValueError('incomplete effective unit properties')
        return values

    def __call__(self, expected):
        fields = {'issue_id','workspace','socket','service_name','socket_name','service_sha256','socket_sha256','native_release','native_binary_sha256'}
        if type(expected) is not dict or set(expected) != fields:
            raise ValueError('exact issue unit evidence required')
        names = ('FragmentPath','DropInPaths','User','Group','WorkingDirectory','ProtectSystem','NoNewPrivileges',
                 'PrivateTmp','PrivateDevices','ProtectHome','ReadWritePaths','RestrictAddressFamilies')
        template = expected['service_name']
        if type(template) is not str or not template.endswith('@.service'):
            raise ValueError('exact issue service template required')
        # systemctl show refuses an uninstantiated template; this fixed instance
        # name loads properties without starting a service or contacting a model.
        instance = template[:-len('@.service')] + '@rras-verification.service'
        service = self.properties(instance, names)
        if (service['FragmentPath'] != str(self.directory / expected['service_name']) or service['DropInPaths'] or
                service['User'] != 'rras-codex-native' or service['Group'] != 'rras-codex-native' or
                service['WorkingDirectory'] != expected['workspace'] or service['ProtectSystem'] != 'strict' or
                any(service[x] != 'yes' for x in ('NoNewPrivileges','PrivateTmp','PrivateDevices','ProtectHome')) or
                service['ReadWritePaths'].split() != [expected['workspace']] or
                set(service['RestrictAddressFamilies'].split()) != {'AF_UNIX','AF_INET','AF_INET6','AF_NETLINK'}):
            raise ValueError('effective issue service isolation differs')
        socket = self.properties(expected['socket_name'], ('FragmentPath','DropInPaths'))
        if socket['FragmentPath'] != str(self.directory / expected['socket_name']) or socket['DropInPaths']:
            raise ValueError('effective issue socket differs')
        if self.verify_sandbox(expected) is not True:
            raise ValueError('current native sandbox proof required')
        return True
