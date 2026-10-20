"""Isolated real Docker/native lifecycle acceptance, not a deployment command.

Load this and sibling deployment tools only from hash-pinned root-owned custody.
All writable files/containers/network belong to the new fixed acceptance fixture.
No production configuration/database/credentials are read or mounted.
"""
import copy
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import traceback
import uuid

ROOT=Path('/var/lib/rras-workflow-upgrade-acceptance-20261020')
PYTHON=Path('/opt/rras-engineering/releases/native-10/venv/bin/python')
IMAGE='sha256:b99f4564d5e17ec0183314c0d2f6f633657cff4916fad0f05f6e7667722da432'


def local(name):
    path=Path(__file__).with_name(name+'.py')
    for item in (path,*path.parents):
        info=item.lstat()
        if item.is_symlink() or info.st_uid!=0 or info.st_mode&0o022:raise ValueError('protected acceptance code required')
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def mkdir(path,mode=0o755,uid=0,gid=0):
    path.mkdir(mode=mode,parents=True);path.chmod(mode);os.chown(path,uid,gid)


def copy_tree(source,target):
    shutil.copytree(source,target)
    for path in target.rglob('*'):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):raise ValueError('regular protected fixture payload required')
        path.chmod(0o755 if path.is_dir() else 0o444)
    target.chmod(0o755)


def actual_network_inspect(network):
    return subprocess.run(['/usr/bin/docker','network','inspect',network],check=True,stdin=subprocess.DEVNULL,capture_output=True,timeout=20).stdout


def run():
    if os.getuid()!=0 or os.geteuid()!=0:raise ValueError('administrator acceptance invocation required')
    s=local('stage_workflow_upgrade');a=local('activate_workflow_upgrade');t=local('upgrade_acceptance_transport')
    s.protected(Path(__file__));s.protected(ROOT.parent);s.protected(PYTHON.resolve(strict=True))
    if ROOT.exists() or ROOT.is_symlink():raise ValueError('acceptance root exists; preserve, never retry')
    source=Path(__file__).resolve().parents[3] # release/engineering/tools/rras_native
    package=source/'payload';bundle=json.loads(s.regular(source/'acceptance-manifest.json'))
    s.protected(package/'vendor');sys.path.insert(0,str(package/'vendor'))
    commit=bundle['source_commit']
    if not re.fullmatch('[0-9a-f]{40}',commit):raise ValueError('exact acceptance source commit required')
    s.source_ancestor(commit);s.idle()
    subprocess.run(['/usr/bin/docker','image','inspect',IMAGE],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,check=True,timeout=20)
    mkdir(ROOT);s.write(ROOT/'started.json',s.encoded({'source_commit':commit,'scope':'isolated-upgrade-acceptance'}))
    token=uuid.uuid4().hex;network='rras-upgrade-test-'+token[:12]+'-net';transport=None;names=None;cases=[];answer=None
    try:
        # Protected paths replace deployment constants only in these freshly loaded
        # private modules. Production defaults/source files remain untouched.
        values={'RELEASES':ROOT/'releases','JOURNALS':ROOT/'upgrades','CONFIG':ROOT/'operator.json',
            'HERMES_CONFIG':ROOT/'data/config.yaml','COMPOSE':ROOT/'compose.yaml','PROFILE':ROOT/'profile.json',
            'CODEX':ROOT/'codex.toml','SBIN':ROOT/'bin','JOURNAL_DB':ROOT/'journal/workflow.sqlite3','HISTORY':ROOT/'history'}
        for key,value in values.items():setattr(s,key,value)
        for path in (s.RELEASES,s.SBIN,ROOT/'artifacts',ROOT/'shared',ROOT/'robot-source'):mkdir(path)
        mkdir(s.HERMES_CONFIG.parent,0o700,1000,1000);mkdir(s.HISTORY,0o750,0,1000);mkdir(s.JOURNAL_DB.parent,0o700)
        # Keep actual global slot/account read-only checks, plus synthetic roles.
        s.ROLE_DIRS={**s.ROLE_DIRS,s.JOURNAL_DB.parent:(0,0,0o700),s.HISTORY:(0,1000,0o750)}
        for path in (s.PROFILE,s.CODEX,s.COMPOSE):s.write(path,b'isolated acceptance fixture\n',0o444)
        s.write(s.CONFIG,s.encoded({'journal':str(s.JOURNAL_DB.parent),'profile':str(s.PROFILE),'codex_config':str(s.CODEX)}))
        manifest=s.decode(s.regular(package/'release-manifest.json'));old=s.RELEASES/'workflow-000000000001';release=s.RELEASES/manifest['release_id']
        copy_tree(package,old);copy_tree(source/'intake',ROOT/'source')
        for name,entry in s.WRAPPERS.items():s.write(s.SBIN/name,s.wrapper(old,entry),0o755)
        original_mounts=s.mounts
        def mounts(installed):
            result=original_mounts(installed)
            remap={'/opt/data':s.HERMES_CONFIG.parent,'/workspace/git/jarvis':ROOT/'source','/workspace/git/robot_ws':ROOT/'robot-source',
                '/workspace/jarvis-artifacts':ROOT/'artifacts','/workspace/shared':ROOT/'shared'}
            return {key:(str(remap.get(key,value[0])),value[1],value[2]) for key,value in result.items()}
        s.mounts=mounts
        history_entry={'command':'/opt/hermes/.venv/bin/python','args':['-I','-B','/opt/rras-workflow/engineering/tools/rras_native/workflow_read_stdio.py','--directory','/opt/rras-workflow-history']}
        prep={'command':'/opt/hermes/.venv/bin/python3','args':['-I','-B','/workspace/git/jarvis/engineering/tools/rras_native/stdio_intake.py',
            '--policy','/workspace/git/jarvis/engineering/config/coding-preparation-policy.json','--state','/opt/data/rras-coding-proposals']}
        servers={name:{'enabled':False,'command':'/bin/false','args':[]} for name in ('hindsight','jarvis-engineering','linear','linear-actions','todoist')}
        servers.update({'rras-workflow-history':history_entry,'rras-coding-preparation':prep})
        s.write(s.HERMES_CONFIG,s.encoded({'mcp_servers':servers,'platforms':{},'cron':{'enabled':False}}));os.chown(s.HERMES_CONFIG,1000,1000)
        # Create and publish a real synthetic journal before starting the gateway.
        def payload_module(name):
            path=old/'engineering/tools/rras_native'/(name+'.py');spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
        j=payload_module('workflow_journal');publisher=payload_module('publish_workflow_views')
        journal=j.Journal(s.JOURNAL_DB.parent,create=True);rows=s.decode(s.regular(source/'fixtures/jarvis-interactive.json'));journal.append(rows)
        assert publisher.publish(journal.root,s.HISTORY,1000)['pages']==1
        baseline_count=len(journal.records());cases.append('nonempty_synthetic_journal_projection')
        names={'hermes','hermes-candidate-'+release.name,'hermes-rollback-'+release.name,'hermes-failed-'+release.name}
        transport=t.Transport(a.api,ROOT,token,IMAGE,names,network)
        # This is a new internal bridge, not the production jarvis-net. No real
        # messaging adapters, credentials, jobs, provider environment or turns.
        subprocess.run(['/usr/bin/docker','network','create','--internal','--driver','bridge','--label',t.LABEL+'='+token,network],
            check=True,stdin=subprocess.DEVNULL,capture_output=True,timeout=30)
        net=s.decode(actual_network_inspect(network))
        if len(net)!=1 or net[0]['Name']!=network or net[0]['Internal'] is not True or net[0]['Driver']!='bridge' or net[0]['Labels'].get(t.LABEL)!=token:raise ValueError('fixture internal network verification failed')
        s.write(ROOT/'namespace.json',s.encoded({'token':token,'network':network,'logical_names':sorted(names)}))
        body={'Image':IMAGE,'User':'1000:1000','Entrypoint':['/opt/hermes/.venv/bin/python'],'Cmd':['-I','-B','/opt/hermes/gateway/run.py'],
            'WorkingDir':'/opt/hermes','Env':[k+'='+v for k,v in t.ENV.items()],'Labels':{t.LABEL:token},
            'HostConfig':{'NetworkMode':network,'Privileged':False,'ReadonlyRootfs':True,'AutoRemove':False,'IpcMode':'private',
                'Memory':1073741824,'NanoCpus':1000000000,'PidsLimit':256,'CapDrop':['ALL'],'SecurityOpt':['no-new-privileges'],'Tmpfs':{'/tmp':'rw,nosuid,nodev,size=128m,mode=1777'},
                'Mounts':[{'Source':v[0],'Target':k,'Type':'bind','ReadOnly':not v[1]} for k,v in mounts(old).items()]},
            'NetworkingConfig':{'EndpointsConfig':{'jarvis-net':{'Aliases':['hermes','jarvis']}}}}
        a.api=transport.call
        initial=transport.call('POST','/containers/create?name=hermes',body);original_id=initial['Id'];transport.call('POST','/containers/'+original_id+'/start')
        actual_command=s.command
        def command(argv,**kwargs):
            if argv[:3]==['/usr/bin/docker','inspect','hermes']:
                return subprocess.CompletedProcess(argv,0,s.encoded([transport.call('GET','/containers/hermes/json')]),b'')
            if argv[:2]==['/usr/bin/docker','exec']:
                value=list(argv);index=5 if value[2]=='-i' else 4
                # Arguments before ref must match the actual reviewed command forms.
                if value[2:index] not in (['-i','--user','1000:1000'],['--user','1000:1000']):raise ValueError('unadmitted fixture exec identity')
                value[index]=transport.exec_ref(value[index])
                if value[index+1:index+5]!=['/opt/hermes/.venv/bin/python','-I','-B','-c']:raise ValueError('unadmitted fixture exec')
                return actual_command(value,**kwargs)
            if argv[0] in ('/usr/bin/git','/usr/bin/systemctl'):return actual_command(argv,**kwargs)
            raise ValueError('unadmitted acceptance subprocess')
        s.command=command
        # Prepare a synthetic plan using the exact runtime payload. No production
        # hash/config is read, and no candidate is usable for production paths.
        candidate=ROOT/'candidate';copy_tree(package,candidate)
        plan={'schema_version':2,'scope':'inactive_upgrade_candidate_only','release':str(release),'source_commit':manifest['source_commit'],
            'installed_release':str(old),'activation_authorized':False,'journal_required':True,'operator_config_action':'preserve_existing_bytes','candidate_registration_applied':False,
            'config_path':str(s.CONFIG),'expected_operator_config_sha256':s.sha(s.regular(s.CONFIG)),
            'profile_sha256':s.sha(s.regular(s.PROFILE)),'codex_config_sha256':s.sha(s.regular(s.CODEX)),
            'hermes':{'image':IMAGE,'compose':str(s.COMPOSE),'expected_config_sha256':s.sha(s.regular(s.HERMES_CONFIG,user=True)),
                'expected_compose_sha256':s.sha(s.regular(s.COMPOSE)),'existing_history_entry_name':'rras-workflow-history','existing_history_entry':history_entry,
                'preserve_other_entries_and_mounts':True,'replace_readonly_mount':{'expected_source':str(old),'source':str(release),'target':'/opt/rras-workflow','read_only':True}}}
        plan_raw=s.encoded(plan);manifest.update(schema_version=2,kind='workflow_upgrade_candidate',plan_sha256=s.sha(plan_raw))
        for path,raw in ((candidate/'install-plan.json',plan_raw),(candidate/'release-manifest.json',s.encoded(manifest))):
            path.chmod(0o600);path.write_bytes(raw)
        digest=s.sha(s.encoded(manifest))
        # Initial readiness uses the real gateway status and actual MCP2 protocol.
        probe=a.Upgrade.__new__(a.Upgrade);probe.s=s;probe.old=transport.call('GET','/containers/hermes/json');probe.plan=plan;probe.release=release
        deadline=time.monotonic()+150
        while True:
            try:
                status=probe.status(original_id)
                if status['fresh'] is True and status['live'] is True and status['state']=='running':break
            except (ValueError,OSError,subprocess.SubprocessError):pass
            if time.monotonic()>=deadline:raise ValueError('isolated gateway did not become ready')
            time.sleep(2)
        plan['hermes']['expected_config_sha256']=s.sha(s.regular(s.HERMES_CONFIG,user=True))
        plan_raw=s.encoded(plan);manifest['plan_sha256']=s.sha(plan_raw)
        for path,raw in ((candidate/'install-plan.json',plan_raw),(candidate/'release-manifest.json',s.encoded(manifest))):path.write_bytes(raw)
        digest=s.sha(s.encoded(manifest))
        s.stage(candidate,digest);engine=a.Upgrade(s.JOURNALS/release.name,digest,stage=s)
        assert engine.preflight()['service_mutations'] is False;cases.append('actual_root_inactive_stage_preflight')
        result=engine.activate(True);assert result['phase']=='complete';cases.extend(['actual_native_fresh_idle_drain','actual_docker_clone_normalization','actual_readonly_mounts_and_mcp_discovery','atomic_fixture_wrapper_upgrade'])
        upgraded=transport.call('GET','/containers/hermes/json');assert upgraded['Id']!=original_id
        # Later legitimate journal/projection changes must survive real rollback.
        records=payload_module('workflow_records');event=copy.deepcopy(rows[-1]);event.update(event_id='evt_'+'f'*32,sequence=2,
            previous_event_sha256=records.record_digest(rows[-1]),event_type='validation.finished',outcome='failed',summary='Synthetic later acceptance event.')
        journal.append([event]);assert publisher.publish(journal.root,s.HISTORY,1000)['pages']==1
        later_db=s.sha(s.regular(s.JOURNAL_DB));later_index=s.sha(s.regular(s.HISTORY/'index.json'))
        assert engine.rollback(True)['phase']=='rolled_back'
        assert s.sha(s.regular(s.JOURNAL_DB))==later_db and s.sha(s.regular(s.HISTORY/'index.json'))==later_index
        assert len(journal.records())==baseline_count+1;cases.append('later_real_sqlite_history_survive_rollback')
        assert transport.call('GET','/containers/hermes/json')['Id']==original_id
        try:engine.activate(True)
        except ValueError:cases.append('activation_replay_refused')
        else:raise ValueError('activation replay not fenced')
        cases.append('retained_original_and_replacement')
        answer={'phase':'isolated_upgrade_lifecycle_verified','root':str(ROOT),'source_commit':commit,'api_calls':0,
            'real_credentials_used':False,'production_configuration_changed':False,'production_journal_changed':False,
            'production_services_mutated':False,'network':'dedicated_internal_bridge','cases':cases,'containers_deleted':False,'automatic_retry':False}
        return answer
    except BaseException:
        try:s.write(ROOT/'acceptance-error.txt',traceback.format_exc().encode()[:65536])
        except OSError:pass
        raise
    finally:
        # Stop only positively labelled, isolated fixture containers. Retain all
        # resources and evidence on success/failure; never delete or touch live Hermes.
        stop_errors=[]
        if transport is not None:
            for name in sorted(names):
                try:
                    row=transport.call('GET','/containers/'+name+'/json')
                    if row is not None and row['State']['Running']:transport.call('POST','/containers/'+row['Id']+'/stop?t=60')
                    row=transport.call('GET','/containers/'+name+'/json')
                    if row is not None and row['State']['Running']:raise ValueError('fixture stop not verified')
                except BaseException:
                    stop_errors.append(name)
                    try:s.write(ROOT/('stop-error-'+uuid.uuid4().hex+'.txt'),traceback.format_exc().encode()[:65536])
                    except OSError:pass
            s.write(ROOT/'docker-operations.json',s.encoded(transport.calls))
        if stop_errors:raise ValueError('fixture stop uncertain; inspect protected evidence')
        if answer is not None:
            answer['fixture_containers_stopped']=True;s.write(ROOT/'complete.json',s.encoded(answer))

if __name__=='__main__':
    try:answer=run()
    except (ValueError,OSError,KeyError,TypeError,AssertionError,subprocess.SubprocessError):
        raise SystemExit('Acceptance stopped; preserve private fixture evidence. No automatic retry or production recovery.')
    print(json.dumps(answer))
