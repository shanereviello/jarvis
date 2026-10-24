"""Build/verify an inactive runtime and installation blueprint. No host mutations."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path,PurePosixPath
import re

SOURCE_FILES=tuple('engineering/tools/rras_history/'+name+'.py' for name in (
    'access','contract','documents','store','unix','interactive','interactive_cli','production_entry','client_entry'))+(
    'engineering/contracts/engineering-history-v1.schema.json',)+tuple(
    'engineering/docs/engineering-history-phase1/templates/'+name+'.md' for name in ('review','checkpoint','completion'))
ARTIFACTS={'deployment/rras-engineering-history.service','deployment/access-policy.json',
           'deployment/install-plan.json','deployment/rras-history-client','deployment/ROLLBACK.md'}


def common():
    spec=importlib.util.spec_from_file_location('history_package_common',Path(__file__).with_name('history_acceptance_package.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def service_unit(release):
    if not re.fullmatch('/opt/rras-engineering/releases/history-[0-9a-f]{12}',release):raise ValueError('exact protected release required')
    return f'''[Unit]
Description=RRAS private engineering history
ConditionPathExists=/var/lib/rras-engineering-history/history.sqlite3
ConditionPathExists=/etc/rras-engineering-history/access-policy.json

[Service]
Type=simple
User=rras-history
Group=rras-history
UMask=0077
Environment=PATH=/usr/bin:/bin HOME=/nonexistent LANG=C.UTF-8
UnsetEnvironment=OPENAI_API_KEY ANTHROPIC_API_KEY GH_TOKEN GITHUB_TOKEN CODEX_HOME
WorkingDirectory={release}
ExecStart=/opt/rras-engineering/releases/native-10/venv/bin/python -I -B {release}/engineering/tools/rras_history/production_entry.py serve
RuntimeDirectory=rras-engineering-history
RuntimeDirectoryMode=0700
RuntimeDirectoryPreserve=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/var/lib/rras-engineering-history /run/rras-engineering-history
InaccessiblePaths=-/var/lib/rras-workflow -/var/lib/rras-coding-control -/var/lib/rras-coding-tasks -/opt/rras-coding-jobs -/etc/rras-engineering/credentials -/run/docker.sock
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


def artifacts(release,payload_sha):
    c=common()
    policy=dict(contract='engineering-history-access.v1',principals=[dict(uid=1000,private_read=['jarvis','robot_ws'],write=['jarvis','robot_ws'])])
    plan=dict(contract='engineering-history-install-plan.v1',scope='inactive-preparation-only',release=release,payload_sha256=payload_sha,
              account=dict(name='rras-history',group='rras-history',uid_selection='allocate-unused-system-id-after-preflight',shell='/usr/sbin/nologin',home='/nonexistent'),
              store='/var/lib/rras-engineering-history',policy='/etc/rras-engineering-history/access-policy.json',
              socket='/run/rras-engineering-history/service.sock',unit='rras-engineering-history.service',
              client_wrapper='/usr/local/bin/rras-history-client',client_uid=1000,
              socket_access='exact-per-uid-posix-acl-before-listen',change_existing_user_groups=False,
              backup_status='deferred-by-operator-2026-10-23-no-verified-recovery',
              initial_data='empty-only-no-synthetic-fixture-import',stage_authorized=False,activation_authorized=False,
              custody=dict(release='root:root directories0755 files0444',config='root:rras-history directory0750 policy0640',
                           store='rras-history:rras-history directory0700 database0600',unit='root:root0644',wrapper='root:root0755',
                           runtime='service-owned0700 plus exact named-client traverse/socket ACLs'),
              installation_journal='/var/lib/rras-history-installations/'+Path(release).name,
              gates=['separate-source-merge','isolated-hardened-unit-and-acl-host-acceptance','operator-backup-deferral-recorded',
                     'explicit-inactive-install-decision','explicit-activation-decision'],
              rollback='disable-and-stop-history-unit-preserve-account-store-config-release-and-spools')
    wrapper=('#!/bin/sh\nexec /opt/rras-engineering/releases/native-10/venv/bin/python -I -B '+release+'/engineering/tools/rras_history/client_entry.py "$@"\n').encode()
    rollback=b'''# Disable-only rollback blueprint

After an explicitly approved installation, stop and disable only
`rras-engineering-history.service`. Verify its process has exited. Do not delete
or restore its SQLite database to an older snapshot: later receipts/history survive.
Retain account, store, configuration, pinned release, runtime evidence and client
spools. Pending clients remain pending until an explicitly reviewed recovery.
Never remove a stale socket without proving its service is stopped and reviewing
that exact retained endpoint. Do not modify Hermes, coding units, root workflow
journal, provider credentials or Docker containers. This blueprint executes nothing.
Future upgrades/downgrades require separate compatibility and exact-state review.
'''
    return {'deployment/rras-engineering-history.service':service_unit(release),'deployment/access-policy.json':c.encoded(policy),
            'deployment/install-plan.json':c.encoded(plan),'deployment/rras-history-client':wrapper,'deployment/ROLLBACK.md':rollback}


def safe_name(name):
    if type(name) is not str:raise ValueError('runtime name required')
    p=PurePosixPath(name)
    if (p.is_absolute() or str(p)!=name or any(v in ('..','.git','__pycache__') for v in p.parts) or
            name.endswith(('.pyc','.pth')) or not(name in SOURCE_FILES or name in ARTIFACTS or name.startswith('vendor/'))):
        raise ValueError('unsafe runtime path')


def payload_identity(files):
    c=common()
    return hashlib.sha256(c.encoded({name:hashlib.sha256(raw).hexdigest() for name,raw in sorted(files.items()) if not name.startswith('deployment/')})).hexdigest()


def build(source,vendor,destination,commit):
    c=common();source=Path(source).resolve(strict=True);vendor=Path(vendor).resolve(strict=True);destination=Path(destination)
    if not re.fullmatch('[0-9a-f]{40}',commit):raise ValueError('exact source commit required')
    files={name:c.regular(source/name) for name in SOURCE_FILES}
    for path in sorted(vendor.rglob('*')):
        if path.is_dir() and not path.is_symlink():continue
        if '__pycache__' in path.parts or path.suffix=='.pyc':continue
        name='vendor/'+path.relative_to(vendor).as_posix();safe_name(name);files[name]=c.regular(path)
    if not any(name.startswith('vendor/') for name in files):raise ValueError('vendored dependencies required')
    digest=payload_identity(files);release='/opt/rras-engineering/releases/history-'+digest[:12]
    files.update(artifacts(release,digest))
    if len(files)>256 or sum(map(len,files.values()))>c.LIMIT:raise ValueError('bounded runtime required')
    manifest=dict(contract='engineering-history-runtime.v1',source_commit=commit,release=release,payload_sha256=digest,
                  stage_authorized=False,activation_authorized=False,files={name:hashlib.sha256(raw).hexdigest() for name,raw in sorted(files.items())})
    destination.mkdir(mode=0o700)
    for name,raw in files.items():
        path=destination/name;path.parent.mkdir(mode=0o700,parents=True,exist_ok=True);path.write_bytes(raw)
    raw=c.encoded(manifest);(destination/'runtime-manifest.json').write_bytes(raw)
    return dict(phase='inactive_history_package_built',files=len(files),release=release,manifest_sha256=hashlib.sha256(raw).hexdigest(),
                stage_authorized=False,activation_authorized=False,host_mutations=False)


def verify(candidate,expected):
    c=common();candidate=Path(candidate)
    if not candidate.is_absolute() or candidate.resolve(strict=True)!=candidate:raise ValueError('canonical runtime candidate required')
    raw=c.regular(candidate/'runtime-manifest.json',256*1024)
    if type(expected) is not str or not re.fullmatch('[0-9a-f]{64}',expected) or hashlib.sha256(raw).hexdigest()!=expected:
        raise ValueError('runtime manifest digest differs')
    manifest=c.decode(raw)
    if (set(manifest)!={'contract','source_commit','release','payload_sha256','stage_authorized','activation_authorized','files'} or
            manifest['contract']!='engineering-history-runtime.v1' or manifest['stage_authorized'] is not False or
            manifest['activation_authorized'] is not False or not re.fullmatch('[0-9a-f]{40}',manifest['source_commit']) or
            type(manifest['files']) is not dict or not (set(SOURCE_FILES)|ARTIFACTS)<=set(manifest['files']) or len(manifest['files'])>256 or
            c.encoded(manifest)!=raw):raise ValueError('invalid inactive runtime manifest')
    files={}
    for name,sha in manifest['files'].items():
        safe_name(name);content=c.regular(candidate/name)
        if hashlib.sha256(content).hexdigest()!=sha:raise ValueError('runtime payload differs')
        files[name]=content
        if sum(map(len,files.values()))>c.LIMIT:raise ValueError('runtime payload exceeds bound')
    if not any(name.startswith('vendor/') for name in files):raise ValueError('runtime vendor missing')
    digest=payload_identity(files);release='/opt/rras-engineering/releases/history-'+digest[:12]
    if digest!=manifest['payload_sha256'] or release!=manifest['release']:raise ValueError('runtime identity differs')
    for name,raw in artifacts(release,digest).items():
        if files[name]!=raw:raise ValueError('installation artifact differs')
    return manifest,files


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',required=True);parser.add_argument('--vendor',required=True)
    parser.add_argument('--destination',required=True);parser.add_argument('--source-commit',required=True)
    args=parser.parse_args()
    print(json.dumps(build(args.source,args.vendor,args.destination,args.source_commit)))
