"""Disposable actual files and hashes; explicit fake ownership/Docker boundaries.

No services, production paths, credentials or network. Fixture root command adapter
supports read-only inspect/history parsing/source ancestry only; other commands fail.
"""
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from test_workflow_production_package import committed_source

ROOT=Path(__file__).resolve().parents[1]

def module():
    s=importlib.util.spec_from_file_location('upgrade',ROOT/'tools/rras_native/stage_workflow_upgrade.py')
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

@pytest.fixture
def fixture(tmp_path):
    m=module();root=tmp_path
    replacements={'RELEASES':root/'releases','JOURNALS':root/'upgrades','SOURCE':root/'source','CONFIG':root/'config/operator.json',
        'HERMES_CONFIG':root/'hermes/config.yaml','COMPOSE':root/'compose.yaml','PROFILE':root/'profile.json','CODEX':root/'codex.toml',
        'PYTHON':root/'python','SBIN':root/'sbin','JOURNAL_DB':root/'journal/workflow.sqlite3','HISTORY':root/'history'}
    patches=[]
    for key,value in replacements.items():
        p=patch.object(m,key,value);p.start();patches.append(p)
    roles={m.JOURNAL_DB.parent:(0,0,0o700),m.HISTORY:(0,1000,0o750)}
    p=patch.object(m,'ROLE_DIRS',roles);p.start();patches.append(p)
    for directory in (m.RELEASES,m.CONFIG.parent,m.HERMES_CONFIG.parent,m.SBIN,m.JOURNAL_DB.parent,m.HISTORY):directory.mkdir(mode=0o700,parents=True,exist_ok=True)
    for path,raw in ((m.PROFILE,b'profile fixture'),(m.CODEX,b'codex fixture'),(m.PYTHON,b'not executable'),
        (m.JOURNAL_DB,b'existing journal bytes must survive'),(m.HISTORY/'index.json',b'{}'),(m.COMPOSE,b'private compose fixture'),
        (m.HERMES_CONFIG,b'private YAML fixture')):path.write_bytes(raw)
    installed=m.RELEASES/'workflow-421ce120c6da';installed.mkdir()
    for name,entry in m.WRAPPERS.items():(m.SBIN/name).write_bytes(m.wrapper(installed,entry))
    config={'journal':str(m.JOURNAL_DB.parent),'profile':str(m.PROFILE),'codex_config':str(m.CODEX),'retained':'PRIVATE_OPERATOR_VALUE'}
    m.CONFIG.write_bytes(m.encoded(config))
    payload={'engineering/tools/rras_native/example.py':b'# fixture source\n','entrypoints/operator.py':b'# fixture entry\n'}
    identity={'source_commit':'a'*40,'files':{k:m.sha(v) for k,v in payload.items()},'dependencies':{'schema_version':1}}
    release_id='workflow-'+m.sha(m.encoded(identity))[:12];release=m.RELEASES/release_id
    plan={'schema_version':2,'scope':'inactive_upgrade_candidate_only','release':str(release),'source_commit':'a'*40,'installed_release':str(installed),
        'activation_authorized':False,'journal_required':True,'operator_config_action':'preserve_existing_bytes','candidate_registration_applied':False,
        'config_path':str(m.CONFIG),'expected_operator_config_sha256':m.sha(m.CONFIG.read_bytes()),'profile_sha256':m.sha(m.PROFILE.read_bytes()),
        'codex_config_sha256':m.sha(m.CODEX.read_bytes()),'hermes':{'image':m.IMAGE,'compose':str(m.COMPOSE),
            'expected_config_sha256':m.sha(m.HERMES_CONFIG.read_bytes()),'expected_compose_sha256':m.sha(m.COMPOSE.read_bytes()),
            'existing_history_entry_name':'rras-workflow-history','existing_history_entry':{'command':'/opt/hermes/.venv/bin/python','args':['-I','-B','/opt/rras-workflow/engineering/tools/rras_native/workflow_read_stdio.py','--directory','/opt/rras-workflow-history']},
            'preserve_other_entries_and_mounts':True,'replace_readonly_mount':{'expected_source':str(installed),'source':str(release),'target':'/opt/rras-workflow','read_only':True}}}
    candidate=root/'candidate';candidate.mkdir()
    for name,data in payload.items():target=candidate/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    manifest={'schema_version':2,'kind':'workflow_upgrade_candidate','release_id':release_id,**identity}
    def seal():
        raw=m.encoded(plan);(candidate/'install-plan.json').write_bytes(raw);manifest['plan_sha256']=m.sha(raw)
        raw=m.encoded(manifest);(candidate/'release-manifest.json').write_bytes(raw);return m.sha(raw)
    digest=seal()
    current={'Id':'b'*64,'Image':m.IMAGE,'Name':'/hermes','State':{'Running':True,'StartedAt':'fixture-start'},'RestartCount':0,
        'Mounts':[{'Destination':target,'Source':values[0],'RW':values[1],'Type':values[2]} for target,values in m.mounts(installed).items()]}
    calls=[]
    def command(argv,**kwargs):
        calls.append(argv)
        if argv[0]=='/usr/bin/git':return SimpleNamespace(stdout=b'')
        if argv[:3]==['/usr/bin/docker','inspect','hermes']:return SimpleNamespace(stdout=m.encoded([current]))
        if argv[:3]==['/usr/bin/docker','exec','-i']:
            data=m.decode(kwargs['input']);assert data['raw']=='private YAML fixture';assert data['entry']==plan['hermes']['existing_history_entry']
            return SimpleNamespace(stdout=b'existing_history_entry_verified\n')
        raise AssertionError('forbidden host operation '+repr(argv))
    for p in (patch.object(m,'administrator'),patch.object(m,'protected',side_effect=lambda path:Path(path)),patch.object(m,'role'),patch.object(m,'idle'),patch.object(m,'command',side_effect=command)):
        p.start();patches.append(p)
    actual=m.regular
    def read(path,limit=4*1024*1024,user=False):return actual(path,limit,user=False) # UID1000 fixtures; production ownership is tested separately.
    p=patch.object(m,'regular',side_effect=read);p.start();patches.append(p)
    try:yield SimpleNamespace(m=m,root=root,candidate=candidate,manifest=manifest,plan=plan,seal=seal,digest=digest,release=release,journal=m.JOURNALS/release_id,container=current,calls=calls)
    finally:
        for p in reversed(patches):p.stop()


def stage(f):return f.m.stage(f.candidate,f.digest)


def test_inactive_upgrade_preserves_live_bytes_and_records_private_rollback(fixture):
    f=fixture;paths=[f.m.CONFIG,f.m.HERMES_CONFIG,f.m.COMPOSE,f.m.JOURNAL_DB,*f.m.SBIN.iterdir()]
    before={p:p.read_bytes() for p in paths};answer=stage(f)
    assert answer['phase']=='inactive_workflow_upgrade_staged' and not answer['services_changed']
    assert before=={p:p.read_bytes() for p in paths}
    assert f.journal.stat().st_mode&0o777==0o700
    assert (f.journal/'operator-config.original').read_bytes()==before[f.m.CONFIG]
    metadata=f.m.decode((f.journal/'filesystem.original.json').read_bytes())
    assert metadata[str(f.m.CONFIG)]['inode']==f.m.CONFIG.stat().st_ino
    assert (f.release/'entrypoints/operator.py').stat().st_mode&0o777==0o644
    assert f.m.inspect(f.journal)['phase']=='staged_inactive_verified'
    assert 'PRIVATE_OPERATOR_VALUE' not in json.dumps(answer)
    assert (f.journal/'wrappers/rras-workflow.candidate').read_bytes()==f.m.wrapper(f.release,'operator.py')
    with pytest.raises(ValueError):stage(f)


@pytest.mark.parametrize('field',['operator','hermes','compose','profile','wrapper','image','mount','drain'])
def test_changed_preconditions_refuse_before_creating_upgrade_roots(fixture,field):
    f=fixture
    if field=='operator':f.m.CONFIG.write_bytes(b'{}')
    elif field=='hermes':f.m.HERMES_CONFIG.write_bytes(b'changed')
    elif field=='compose':f.m.COMPOSE.write_bytes(b'changed')
    elif field=='profile':f.m.PROFILE.write_bytes(b'changed')
    elif field=='wrapper':(f.m.SBIN/'rras-workflow').write_bytes(b'changed')
    elif field=='image':f.container['Image']='other'
    elif field=='mount':f.container['Mounts'][0]['RW']=False
    else:(f.m.HERMES_CONFIG.parent/'.drain_request.json').write_bytes(b'preserve marker')
    with pytest.raises(ValueError):stage(f)
    assert not f.release.exists() and not f.journal.exists()


@pytest.mark.parametrize('field',['payload','manifest','plan','old_schema','mount_target'])
def test_invalid_candidate_refused_without_live_observation(fixture,field):
    f=fixture
    if field=='payload':(f.candidate/'entrypoints/operator.py').write_bytes(b'changed')
    elif field=='manifest':(f.candidate/'release-manifest.json').write_bytes(b'{}')
    elif field=='plan':(f.candidate/'install-plan.json').write_bytes(b'{}')
    elif field=='old_schema':f.manifest['schema_version']=1;f.digest=f.seal()
    else:f.plan['hermes']['replace_readonly_mount']['target']='/opt/data';f.digest=f.seal()
    with pytest.raises(ValueError):stage(f)
    assert not f.calls and not f.journal.exists()


def test_busy_slot_refused_without_writes(fixture):
    f=fixture
    with patch.object(f.m,'idle',side_effect=ValueError('busy')),pytest.raises(ValueError):stage(f)
    assert not f.journal.exists()


def test_failure_preserves_incomplete_roots_and_inspection_never_adopts(fixture):
    f=fixture;actual=f.m.write
    def write(path,raw,mode=0o600):
        if path.name=='operator.py':raise OSError('fixture interrupted copy')
        return actual(path,raw,mode)
    with patch.object(f.m,'write',side_effect=write),pytest.raises(OSError):stage(f)
    assert f.release.exists() and (f.journal/'started.json').exists() and not (f.journal/'staged.json').exists()
    assert (f.journal/'staging-error.txt').exists()
    assert f.m.inspect(f.journal)['phase']=='incomplete_stage_preserved'
    with pytest.raises(ValueError):stage(f)


@pytest.mark.parametrize('member',['code','private_copy','plan','receipt'])
def test_inspection_refuses_tampered_code_or_rollback_evidence(fixture,member):
    f=fixture;stage(f)
    path={'code':f.release/'entrypoints/operator.py','private_copy':f.journal/'operator-config.original','plan':f.journal/'install-plan.json','receipt':f.journal/'release-manifest.json'}[member]
    path.write_bytes(b'changed')
    with pytest.raises((ValueError,KeyError)):f.m.inspect(f.journal)


def test_changed_live_container_is_reported_without_recovery_mutation(fixture):
    f=fixture;stage(f);f.container['Id']='c'*64
    assert f.m.inspect(f.journal)['phase']=='external_state_changed'
    assert not any('start' in call or 'stop' in call or 'rename' in call for call in f.calls)


def test_journal_change_during_staging_preserves_failure_without_reset(fixture):
    f=fixture;actual=f.m.observe;count=[0]
    def observe(plan):
        count[0]+=1
        if count[0]==2:f.m.JOURNAL_DB.write_bytes(b'concurrent fixture import')
        return actual(plan)
    with patch.object(f.m,'observe',side_effect=observe),pytest.raises(ValueError):stage(f)
    assert f.m.JOURNAL_DB.read_bytes()==b'concurrent fixture import'
    assert f.m.inspect(f.journal)['phase']=='incomplete_stage_preserved'


def test_nonempty_database_sidecar_defers_staging(fixture):
    f=fixture;Path(str(f.m.JOURNAL_DB)+'-journal').write_bytes(b'pending writer')
    with pytest.raises(ValueError):stage(f)
    assert not f.journal.exists()


def test_unprivileged_stager_refuses_before_commands():
    m=module()
    with patch.object(m.os,'getuid',return_value=1000),patch.object(m.os,'geteuid',return_value=1000),patch.object(m,'command',side_effect=AssertionError('no host operations')),pytest.raises(ValueError):
        m.stage('/unused','0'*64)


def test_real_builder_upgrade_candidate_is_accepted_without_host_access(committed_source,tmp_path):
    from test_workflow_production_package import upgrade_inputs
    builder,repo,commit,_=committed_source;out=tmp_path/'real-upgrade';answer=builder.build(repo,commit,out,upgrade_inputs())
    m=module()
    with patch.object(m,'command',side_effect=AssertionError('candidate parsing must not contact host')):
        manifest,raw,plan,plan_raw,payload=m.candidate(out,answer['manifest_sha256'])
    assert manifest['source_commit']==commit and plan['installed_release']==upgrade_inputs()['installed_release']
    assert 'engineering/tools/rras_native/validation_execution.py' in payload


def test_failed_initial_receipt_is_never_adopted(fixture):
    f=fixture;actual=f.m.write
    def write(path,raw,mode=0o600):
        if path.name=='started.json':raise OSError('fixture initial receipt failure')
        return actual(path,raw,mode)
    with patch.object(f.m,'write',side_effect=write),pytest.raises(OSError):stage(f)
    assert f.journal.exists() and not (f.journal/'started.json').exists()
    assert f.m.inspect(f.journal)['phase']=='unidentified_stage_preserved'
    with pytest.raises(ValueError):stage(f)


def test_changed_wrapper_permissions_are_not_silently_accepted(fixture):
    f=fixture;stage(f);(f.m.SBIN/'rras-workflow').chmod(0o700)
    assert f.m.inspect(f.journal)['phase']=='external_state_changed'
