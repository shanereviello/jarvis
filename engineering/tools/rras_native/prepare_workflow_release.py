"""Prepare an absent immutable production candidate/plan; never installs/activates.

Read committed source through Git and copy exact offline dependency bytes. No
pip/network, fake worker, credential, live config write, service or model call.
"""
import argparse
import ast
import hashlib
import importlib.metadata
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import sys

MODULES = tuple(name + '.py' for name in (
    'activity', 'approval', 'approved_launch', 'credentials', 'draft_pr_connector',
    'managed_events', 'manual_runner', 'native_observation', 'native_task_cli',
    'operator_control', 'post_validation', 'publication', 'publication_capture',
    'publication_custody', 'publication_handoff', 'publication_policy',
    'publication_transport', 'publish_workflow_views', 'repository_admission',
    'review_gate', 'task_contract', 'validation_execution', 'validation_workspace',
    'wait_worker', 'workflow_finish', 'workflow_journal', 'workflow_publication',
    'workflow_read_stdio', 'workflow_read_tools', 'workflow_records'))
ASSETS = ('draft_pr_frontend.js', 'draft_pr_operator.js')

PROFILE = '/opt/rras-engineering/releases/operator-project-trust-v1/profile.json'
PROFILE_SHA = 'd6559b7171ff3c9317e05040efd0d8b01f6ae1cca1f45f7c7e1f9a461d4ef64f'
CODEX = '/opt/rras-engineering/releases/operator-project-trust-v1/codex-config.toml'
CODEX_SHA = '15920278361773ab24336a2bb4c48f9a8d5f15c117d6a02ba1c88075b1fe3990'
HERMES_IMAGE = 'sha256:b99f4564d5e17ec0183314c0d2f6f633657cff4916fad0f05f6e7667722da432'
HERMES_CONFIG_SHA = '3a5fcca5b4b53829a5705a7b7bb7af82a591fa99ce3acf7cd114b74338a4aa33'


def activity():
    spec = importlib.util.spec_from_file_location('activity', Path(__file__).with_name('activity.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def committed(source, commit, name):
    return activity().git(source, 'show', commit + ':' + name)


def offline_dependencies(lock):
    if lock['schema_version'] != 1 or sys.version.split()[0] != lock['python']:
        raise ValueError('locked builder interpreter required')
    result = {}
    for name, version in lock['distributions'].items():
        distribution = importlib.metadata.distribution(name)
        if distribution.version != version:
            raise ValueError('offline dependency version changed')
        base = Path(distribution.locate_file('')).resolve()
        for entry in distribution.files or []:
            path = Path(distribution.locate_file(entry)).resolve()
            try:
                relative = path.relative_to(base)
            except ValueError:
                continue  # No console scripts outside site-packages.
            if '__pycache__' in relative.parts or path.suffix == '.pyc' or not path.is_file():
                continue
            if any(p.endswith('.dist-info') for p in relative.parts):
                if path.name not in {'METADATA', 'WHEEL', 'top_level.txt', 'LICENSE', 'LICENSE.txt'} and 'licenses' not in relative.parts:
                    continue  # No direct_url, installer provenance or host RECORD paths.
            if '..' in relative.parts:
                raise ValueError('unsafe dependency member')
            result['vendor/' + relative.as_posix()] = path.read_bytes()
    return result


def wrapper(module, *, managed=False):
    checks = '''
if len(sys.argv)>1 and sys.argv[1] in {'capture','review','approve','launch'}:
    try: config=sys.argv[sys.argv.index('--config')+1]
    except (ValueError,IndexError): raise SystemExit('Explicit protected configuration required')
    if 'journal' not in m.configuration(config)[0]: raise SystemExit('Installed managed workflow requires a journal')
''' if managed else ''
    return ('''import importlib.util,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'vendor'))
p=root/'engineering/tools/rras_native/''' + module + ''''
s=importlib.util.spec_from_file_location('entry',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
''' + checks + '\nm.main()\n').encode()


def verify_module_closure(files):
    """Refuse omitted literal sibling imports before writing a candidate.

    Dynamic dispatch still requires source review; this audits the supported
    local()/with_name() conventions rather than claiming a Python import sandbox.
    """
    prefix='engineering/tools/rras_native/'
    for name in MODULES:
        tree=ast.parse(files[prefix+name])
        for node in ast.walk(tree):
            if not isinstance(node,ast.Call) or not node.args or not isinstance(node.args[0],ast.Constant):continue
            value=node.args[0].value
            if not isinstance(value,str):continue
            function=node.func.id if isinstance(node.func,ast.Name) else node.func.attr if isinstance(node.func,ast.Attribute) else ''
            target=value+'.py' if function=='local' else value if function=='with_name' and value.endswith('.py') else None
            if target is not None and prefix+target not in files:
                raise ValueError('unpackaged local dependency: '+target)


def frontend_entrypoint(files):
    prefix='engineering/tools/rras_native/'
    bridge=files[prefix+'draft_pr_frontend.js'].decode().strip()
    operator=files[prefix+'draft_pr_operator.js'].decode().strip()
    return ('(async function(options) { const bridge = '+bridge+'; const operator = '+operator+
        '; return await operator({...options, bridge}); })\n').encode()


def upgrade_plan(base, upgrade):
    fields={'installed_release','operator_config_sha256','hermes_config_sha256','hermes_compose_sha256'}
    if not isinstance(upgrade,dict) or set(upgrade)!=fields:
        raise ValueError('exact upgrade preconditions required')
    installed=upgrade['installed_release']
    if (not isinstance(installed,str) or not re.fullmatch('/opt/rras-engineering/releases/workflow-[0-9a-f]{12}',installed)
            or installed==base['release']):raise ValueError('different existing workflow release required')
    for key in fields-{'installed_release'}:
        if not isinstance(upgrade[key],str) or not re.fullmatch('[0-9a-f]{64}',upgrade[key]):raise ValueError('exact current-state digests required')
    return {'schema_version':2,'scope':'inactive_upgrade_candidate_only',
        'release':base['release'],'source_commit':base['source_commit'],'installed_release':installed,
        'journal_required':True,'config_path':base['config_path'],
        'operator_config_action':'preserve_existing_bytes','expected_operator_config_sha256':upgrade['operator_config_sha256'],
        'candidate_registration_applied':False,'profile_sha256':PROFILE_SHA,'codex_config_sha256':CODEX_SHA,
        'preserve_paths':[base['config_path'],PROFILE,CODEX,'/var/lib/rras-workflow/journal',
            '/var/lib/rras-workflow/history','/var/lib/rras-coding-control','/opt/rras-coding-jobs',
            '/var/lib/rras-coding-tasks','/etc/rras-engineering/credentials'],
        'hermes':{'image':HERMES_IMAGE,'expected_config_sha256':upgrade['hermes_config_sha256'],
            'expected_compose_sha256':upgrade['hermes_compose_sha256'],'compose':base['hermes']['compose'],
            'existing_history_entry_name':'rras-workflow-history','existing_history_entry':base['hermes']['new_entry'],
            'replace_readonly_mount':{'expected_source':installed,'source':base['release'],
                'target':'/opt/rras-workflow','read_only':True},'preserve_other_entries_and_mounts':True},
        'entrypoint_updates':['/usr/local/sbin/rras-workflow','/usr/local/sbin/rras-workflow-journal','/usr/local/sbin/rras-workflow-publish'],
        'operator_frontend':base['release']+'/entrypoints/draft-pr-frontend.js',
        'activation_requires':['approved_source_merge','separate_installation_decision',
            'root_protected_current_state_digest_verification','global_task_slot_and_uid996_idle',
            'native_gateway_drain_and_idle','private_rollback_of_config_compose_entrypoints_and_container',
            'journal_and_approval_state_preserved','dedicated_upgrade_installer_and_post_switch_verification'],
        'installer_implemented':False,'api_calls':0,'activation_authorized':False}


def build(source, commit, output, upgrade=None):
    a = activity()
    source = a.canonical_repo(source)
    if not re.fullmatch('[0-9a-f]{40}', commit) or a.git(source, 'rev-parse', 'HEAD').decode().strip() != commit:
        raise ValueError('exact current source commit required')
    output = Path(output)
    if not output.is_absolute() or output.exists() or output.is_symlink():
        raise ValueError('absent absolute candidate required')
    lock = json.loads(committed(source, commit, 'engineering/config/workflow-dependency-lock.json'))
    files = {'engineering/tools/rras_native/' + name: committed(source, commit, 'engineering/tools/rras_native/' + name) for name in MODULES}
    files.update({'engineering/tools/rras_native/'+name: committed(source,commit,'engineering/tools/rras_native/'+name) for name in ASSETS})
    verify_module_closure(files)
    files['engineering/contracts/workflow-v1.schema.json'] = committed(source, commit, 'engineering/contracts/workflow-v1.schema.json')
    files['config/jarvis-registration.json'] = committed(source, commit, 'engineering/config/jarvis-registration.candidate.json')
    files['config/workflow-dependency-lock.json'] = a.encoded(lock)
    files.update(offline_dependencies(lock))
    files['entrypoints/operator.py'] = wrapper('operator_control.py', managed=True)
    files['entrypoints/journal.py'] = wrapper('workflow_journal.py')
    files['entrypoints/publish.py'] = wrapper('publish_workflow_views.py')
    files['entrypoints/draft-pr.py'] = wrapper('draft_pr_connector.py')
    files['entrypoints/draft-pr-frontend.js'] = frontend_entrypoint(files)
    if b'def _run(' not in files['engineering/tools/rras_native/manual_runner.py'] or b'fake-ready.json' in files['engineering/tools/rras_native/manual_runner.py']:
        raise ValueError('production coding runner required; never stage the acceptance fake')
    hashes = {name: a.digest(raw) for name, raw in sorted(files.items())}
    identity = {'source_commit': commit, 'files': hashes, 'dependencies': lock}
    release_id = 'workflow-' + a.digest(a.encoded(identity))[:12]
    release = '/opt/rras-engineering/releases/' + release_id
    config = {'schema_version': 1, 'registration': json.loads(files['config/jarvis-registration.json']),
              'hermes_project': 'jarvis', 'profile': PROFILE, 'codex_config': CODEX,
              'journal': '/var/lib/rras-workflow/journal'}
    entry = {'command': '/opt/hermes/.venv/bin/python', 'args': ['-I', '-B',
        '/opt/rras-workflow/engineering/tools/rras_native/workflow_read_stdio.py',
        '--directory', '/opt/rras-workflow-history']}
    plan = {'schema_version': 1, 'scope': 'inactive_candidate_only', 'release': release,
            'source_commit': commit, 'journal_required': True,
            'config_path': '/etc/rras-engineering/workflow/jarvis.json', 'operator_config': config,
            'profile_sha256': PROFILE_SHA, 'codex_config_sha256': CODEX_SHA,
            'journal': {'path': config['journal'], 'uid': 0, 'gid': 0, 'mode': '0700'},
            'projections': {'path': '/var/lib/rras-workflow/history', 'uid': 0, 'gid': 1000, 'mode': '0750', 'files_mode': '0440'},
            'hermes': {'image': HERMES_IMAGE, 'expected_config_sha256': HERMES_CONFIG_SHA,
                'compose': '/opt/hermes/releases/hermes-0c8b6be07ce8/deploy/hermes/compose.yaml',
                'new_entry_name': 'rras-workflow-history', 'new_entry': entry,
                'add_readonly_mounts': [{'source': release, 'target': '/opt/rras-workflow', 'read_only': True},
                    {'source': '/var/lib/rras-workflow/history', 'target': '/opt/rras-workflow-history', 'read_only': True}]},
            'activation_requires': ['approved_source_merge', 'protected_preflight', 'separate_installation_decision',
                'native_gateway_drain_and_idle', 'preserved_private_configuration_and_container_rollback'],
            'api_calls': 0, 'activation_authorized': False}
    if upgrade is not None:plan=upgrade_plan(plan,upgrade)
    manifest = {'schema_version': 2 if upgrade is not None else 1, 'kind': 'workflow_upgrade_candidate' if upgrade is not None else 'workflow_production_candidate', 'release_id': release_id,
                **identity, 'plan_sha256': a.digest(a.encoded(plan))}
    output.mkdir(mode=0o700)
    for name, raw in files.items():
        p = PurePosixPath(name)
        if p.is_absolute() or '..' in p.parts:
            raise ValueError('unsafe package member')
        path = output / name
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        a.absent(path, raw)
    a.absent(output / 'install-plan.json', a.encoded(plan))
    a.absent(output / 'release-manifest.json', a.encoded(manifest))
    return {'candidate': str(output), 'release': release, 'source_commit': commit,
            'manifest_sha256': a.digest(a.encoded(manifest)), 'files': len(files),
            'activation_authorized': False}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'commit', 'output'):
        p.add_argument('--' + name, required=True)
    p.add_argument('--upgrade-from')
    for name in ('operator-config-sha256','hermes-config-sha256','hermes-compose-sha256'):p.add_argument('--'+name)
    args = p.parse_args(argv)
    values=[args.upgrade_from,args.operator_config_sha256,args.hermes_config_sha256,args.hermes_compose_sha256]
    if any(values) and not all(values):p.error('all four upgrade preconditions required')
    upgrade=dict(zip(('installed_release','operator_config_sha256','hermes_config_sha256','hermes_compose_sha256'),values)) if all(values) else None
    print(json.dumps(build(args.source, args.commit, args.output,upgrade)))


if __name__ == '__main__':
    main()
