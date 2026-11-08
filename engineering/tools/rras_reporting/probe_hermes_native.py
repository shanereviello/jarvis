"""Offline installed Hermes context/SELECT-only capture probe, synthetic DB only."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

ROOT=Path(__file__).resolve().parents[3]
IMAGE='sha256:b99f4564d5e17ec0183314c0d2f6f633657cff4916fad0f05f6e7667722da432'


def local(name):
    spec=importlib.util.spec_from_file_location('hermes_native_probe_'+name,Path(__file__).with_name(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def inside():
    # No production mounts or default native home. Constructor writes below
    # create synthetic source only; the collector opens it strictly read-only.
    from hermes_state import SessionDB
    from gateway import session_context
    root=Path('/tmp/hermes-selected-fixture');root.mkdir(mode=0o700)
    org=str(uuid.UUID(int=1));session=str(uuid.UUID(int=5));alias='linear:'+org+':'+session;run='run_'+'a'*32
    os.environ.update(HERMES_SESSION_PLATFORM='api_server',HERMES_SESSION_ID=alias,HERMES_SESSION_KEY=run)
    try:local('hermes_native_context').actual()
    except ValueError:pass
    else:raise ValueError('unbound environment fallback was accepted')
    tokens=session_context.set_session_vars(platform='api_server',chat_id=alias,session_id='selected-compression-tip',session_key=run)
    try:
        assert local('hermes_native_context').actual()==dict(organization_id=org,session_id=session,hermes_session_id=alias,run_id=run)
        assert local('hermes_native_context').capture_identity()['native_session_id']=='selected-compression-tip'
    finally:session_context.clear_session_vars(tokens)
    path=root/'state.db';db=SessionDB(db_path=path)
    try:
        db.create_session(alias,'api_server');db.append_message(alias,'user','SELECTED-VISIBLE-REQUEST')
        db.append_message(alias,'assistant','SELECTED-VISIBLE-REPLY',reasoning='EXCLUDED-PRIVATE-REASONING')
        db.create_session('unrelated-source','api_server');db.append_message('unrelated-source','user','EXCLUDED-UNSELECTED-CONTENT')
        db.publish_compression_child(parent_session_id=alias,child_session_id='selected-compression-tip',source='api_server',
            messages=[dict(role='assistant',content='Selected native compression handoff.')],require_compression_lease=False)
        db.append_message('selected-compression-tip','user','SELECTED-AFTER-COMPRESSION')
    finally:db.close()
    before=hashlib.sha256(path.read_bytes()).hexdigest()
    snapshot=local('hermes_readonly').selected(path,alias,'Synthetic isolated native fixture only')
    assert snapshot['lineage_session_ids']==[alias,'selected-compression-tip']
    assert 'unrelated-source' not in json.dumps(snapshot) and 'EXCLUDED-UNSELECTED-CONTENT' not in json.dumps(snapshot)
    collector=local('capture_collectors');spool=local('capture_intake').Spool(root/'exports',create=True)
    result=collector.collect_hermes(spool,snapshot=snapshot,exporter='/opt/hermes/hermes_cli/session_export_md.py',
        scope=dict(kind='repository',id='jarvis'),context=None,authorization_reference='Synthetic isolated native fixture only')
    with spool.connection() as db:row=db.execute("SELECT export_sha256 FROM items WHERE kind='artifact'").fetchone()
    export=(spool.exports/row[0]).read_text()
    assert all(value in export for value in ('SELECTED-VISIBLE-REQUEST','SELECTED-VISIBLE-REPLY','SELECTED-AFTER-COMPRESSION'))
    assert all(value not in export for value in ('EXCLUDED-PRIVATE-REASONING','EXCLUDED-UNSELECTED-CONTENT'))
    assert hashlib.sha256(path.read_bytes()).hexdigest()==before
    try:local('hermes_readonly').selected(path,alias[:-1],'Synthetic exact-ID refusal fixture')
    except ValueError:pass
    else:raise ValueError('prefix selection was accepted')
    print(json.dumps(dict(installed_native_reader=True,read_only_source_bytes_preserved=True,
        native_context_bound=True,environment_fallback_denied=True,exact_linear_alias=True,compression_lineage=True,rotated_native_id_distinguished=True,
        unrelated_session_excluded=True,reasoning_excluded=True,native_renderer=True,
        real_sessions_exported=0,models_started=0,production_mounts=False)))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--inside',action='store_true');parser.add_argument('--isolated-containers',action='store_true');args=parser.parse_args()
    if args.inside:inside();return
    if not args.isolated_containers:parser.error('explicit isolated fixture required')
    name='rras-hermes-selected-'+uuid.uuid4().hex[:10]
    argv=['docker','run','--rm','--pull=never','--name',name,'--network','none','--read-only','--cap-drop','ALL',
        '--security-opt','no-new-privileges:true','--user','1000:1000','--tmpfs','/tmp:rw,nosuid,nodev,size=128m,mode=1777',
        '--mount','type=bind,source='+str(ROOT/'engineering')+',target=/fixture/engineering,readonly','--entrypoint','/usr/bin/env',IMAGE,
        '-i','PATH=/usr/bin:/bin','HOME=/tmp/fixture-home','HERMES_HOME=/tmp/fixture-home','LANG=C.UTF-8',
        '/opt/hermes/.venv/bin/python','-B','/fixture/engineering/tools/rras_reporting/probe_hermes_native.py','--inside']
    try:
        result=subprocess.run(argv,capture_output=True,text=True,timeout=50)
        if result.returncode:raise ValueError('isolated Hermes native capture failed: '+result.stderr[-2500:])
        print(result.stdout.strip())
    finally:subprocess.run(['docker','rm','-f',name],capture_output=True,timeout=15)


if __name__=='__main__':main()
