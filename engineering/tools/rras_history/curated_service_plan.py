"""Fixed hardened curated read-unit blueprint. No host writes or installation."""
import re


def service_unit(release):
    if type(release) is not str or not re.fullmatch('/opt/rras-engineering/releases/curated-history-[0-9a-f]{12}',release):
        raise ValueError('exact protected curated release required')
    return f'''[Unit]
Description=RRAS curated engineering history read endpoint
ConditionPathExists=/var/lib/rras-curated-history/catalog/configuration.json
ConditionPathExists=/etc/rras-curated-history/read-policy.json

[Service]
Type=simple
User=rras-history
Group=rras-history
UMask=0077
Environment=PATH=/usr/bin:/bin HOME=/nonexistent LANG=C.UTF-8
UnsetEnvironment=OPENAI_API_KEY ANTHROPIC_API_KEY GH_TOKEN GITHUB_TOKEN CODEX_HOME
WorkingDirectory={release}
ExecStart=/opt/rras-engineering/releases/native-10/venv/bin/python -I -B {release}/engineering/tools/rras_history/curated_service_entry.py --account 995
RuntimeDirectory=rras-curated-history
RuntimeDirectoryMode=0700
RuntimeDirectoryPreserve=yes
ProtectSystem=strict
ProtectHome=yes
ReadOnlyPaths=/var/lib/rras-curated-history/catalog
ReadWritePaths=/run/rras-curated-history
InaccessiblePaths=-/var/lib/rras-engineering-history -/etc/rras-engineering-history -/run/rras-engineering-history -/var/lib/rras-workflow -/var/lib/rras-coding-control -/var/lib/rras-coding-tasks -/opt/rras-coding-jobs -/etc/rras-engineering/credentials -/run/docker.sock
PrivateNetwork=yes
RestrictAddressFamilies=AF_UNIX
PrivateTmp=yes
PrivateDevices=yes
NoNewPrivileges=yes
CapabilityBoundingSet=
AmbientCapabilities=
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectKernelLogs=yes
ProtectControlGroups=yes
ProtectClock=yes
ProtectProc=invisible
ProcSubset=pid
RestrictNamespaces=yes
RestrictSUIDSGID=yes
RestrictRealtime=yes
LockPersonality=yes
MemoryDenyWriteExecute=yes
SystemCallArchitectures=native
SystemCallFilter=@system-service
SystemCallErrorNumber=EPERM
TasksMax=32
MemoryMax=512M
LimitNOFILE=128
Restart=no
TimeoutStopSec=15s
KillMode=control-group

[Install]
WantedBy=multi-user.target
'''.encode()
