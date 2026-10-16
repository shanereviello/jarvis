"""Root, model-free filesystem acceptance of publication custody. No worker launch."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import uuid


def local(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def probe():
    if os.geteuid()!=0:raise ValueError('administrator acceptance required')
    a=local('activity');capture=local('publication_capture');launch=local('approved_launch')
    launch.slot()
    run_id=uuid.uuid4().hex
    root=Path('/var/lib')/('rras-publication-acceptance-'+run_id)
    launch.trusted(root.parent);root.mkdir(mode=0o700)
    print('RETAIN RUN_ID='+run_id+' WORK='+str(root),flush=True)
    result={'scope':'publication-custody-model-free-filesystem','run_id':run_id,'success':False,
            'api_calls':0,'real_credentials_used':False,'worker_launched':False,
            'installed_services_modified':False,'cases':[]}
    try:
        state=root/'control';state.mkdir(mode=0o700)
        work=root/'worker/work';work.mkdir(parents=True,mode=0o700)
        review={'request':{'task_id':'TASK-publication-fixture'},'submission_id':'fixture-only'}
        review_id=a.digest(a.encoded(review));auth=uuid.uuid4().hex
        link={'authorization_id':auth,'review_id':review_id,'submission_id':'fixture-only','run_id':run_id,'work':str(work)}
        for name,obj in [(review_id+'.review.json',review),(auth+'.launch.json',link),(auth+'.result.json',{**link,'service_exit':0,'host_stop_verified':True})]:a.absent(state/name,a.encoded(obj))
        payload=b'harmless publication fixture; not source code\n'
        manifest={'files':{'changes.patch':{'sha256':a.digest(payload),'size_bytes':len(payload)}}}
        export_id=a.digest(a.encoded(manifest));export=work/'index/TASK-publication-fixture/exports'/export_id
        export.mkdir(parents=True,mode=0o700)
        evidence={'export':{'export_id':export_id,'path':str(export)}}
        for path,data in [(work/'evidence.json',a.encoded(evidence)),(export/'manifest.json',a.encoded(manifest)),(export/'changes.patch',payload)]:
            a.absent(path,data);os.chown(path,996,996)
        # Only this freshly created fixture subtree receives worker ownership.
        for path in [root/'worker',*(root/'worker').rglob('*')]:os.chown(path,996,996,follow_symlinks=False)
        receipt=capture.capture(state,auth,root/'custody')
        assert (root/'custody/artifacts/changes.patch').read_bytes()==payload
        assert (root/'custody').stat().st_uid==0 and (root/'custody').stat().st_mode&0o777==0o700
        result['cases'].extend(['real_uid996_input','protected_custody','exact_artifact_copy','trusted_run_branch_assignment'])
        def refuses(name,operation):
            try:operation()
            except (ValueError,FileExistsError):result['cases'].append(name)
            else:raise AssertionError('refusal missing: '+name)
        refuses('existing_custody_preserved',lambda:capture.capture(state,auth,root/'custody'))
        patch=export/'changes.patch';patch.write_bytes(b'altered')
        refuses('altered_artifact_refused',lambda:capture.capture(state,auth,root/'altered'))
        patch.write_bytes(payload);patch.chmod(0o666)
        refuses('writable_file_refused',lambda:capture.capture(state,auth,root/'writable'))
        patch.chmod(0o600);patch.unlink();patch.symlink_to(work/'evidence.json')
        refuses('symlink_refused',lambda:capture.capture(state,auth,root/'symlink'))
        patch.unlink();a.absent(patch,payload) # Root-owned input must also be refused.
        refuses('wrong_owner_refused',lambda:capture.capture(state,auth,root/'owner'))
        assert not any((root/name).exists() for name in ('altered','writable','symlink','owner'))
        result['cases'].append('failed_capture_allocates_no_custody')
        result['success']=True
    except Exception as e:result['error_type']=type(e).__name__
    finally:a.absent(root/'acceptance.json',a.encoded(result))
    print(json.dumps(result));return result

if __name__=='__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    raise SystemExit(0 if probe()['success'] else 1)
