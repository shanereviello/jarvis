"""Render inactive native App Server units with one exact writable checkout.

Installation, policy activation and credential preparation are separate operator
operations. These definitions reuse the existing service identity and credential.
"""
import importlib.util
from pathlib import Path
import re


def runtime():
    spec=importlib.util.spec_from_file_location('issue_units_runtime',Path(__file__).with_name('codex_runtime.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def render(issue,workspace,native_release):
    runtime().identifier(issue)
    for item in (workspace,native_release):
        if (type(item) is not str or not re.fullmatch(r'/[A-Za-z0-9_./-]+',item) or
                Path(item).resolve()!=Path(item) or '..' in Path(item).parts or item=='/'):
            raise ValueError('canonical systemd-safe absolute paths required')
    stem='rras-codex-issue-'+issue
    socket='/run/rras-codex-runtime/coding-'+issue+'.sock'
    service='''[Unit]
Description=Scoped Codex App Server for issue {issue} (%i)
ConditionPathExists=/etc/rras-engineering/codex-runtime/host-runtime-enabled
ConditionPathExists=/var/lib/rras-codex-native/codex/config.toml

[Service]
User=rras-codex-native
Group=rras-codex-native
UMask=0077
WorkingDirectory={workspace}
StandardInput=socket
StandardOutput=socket
StandardError=null
StateDirectory=rras-codex-native
StateDirectoryMode=0700
LoadCredential=openai-api-key:/etc/rras-engineering/codex-runtime/openai-api-key
ExecStartPre=/usr/bin/install -d -m 0700 /var/lib/rras-codex-native/codex
ExecStart={release}/venv/bin/python -I {release}/engineering/tools/rras_reporting/codex_app_server_entry.py --binary {release}/runtime/bin/codex --codex-home /var/lib/rras-codex-native/codex
NoNewPrivileges=yes
CapabilityBoundingSet=
AmbientCapabilities=
PrivateTmp=yes
PrivateDevices=yes
ProtectHome=yes
ProtectSystem=strict
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
ProtectClock=yes
LockPersonality=yes
RestrictSUIDSGID=yes
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6 AF_NETLINK
ReadWritePaths={workspace}
TimeoutStartSec=30s
TimeoutStopSec=10s
MemoryMax=4G
TasksMax=256
KillMode=control-group
'''.format(issue=issue,workspace=workspace,release=native_release)
    listener='''[Unit]
Description=Private Codex App Server socket for issue {issue}
ConditionPathExists=/etc/rras-engineering/codex-runtime/host-runtime-enabled

[Socket]
ListenStream={socket}
SocketUser=rras-codex-adapter
SocketGroup=rras-codex-adapter
SocketMode=0600
DirectoryMode=0750
Accept=yes
RemoveOnStop=yes

[Install]
WantedBy=sockets.target
'''.format(issue=issue,socket=socket)
    return dict(service_name=stem+'@.service',service=service,socket_name=stem+'.socket',listener=listener,socket_path=socket)
