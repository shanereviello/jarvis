"""No-turn native instruction compatibility plus credential-free fake-worker cases."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import tomllib


def local(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def run(source,python,binary,profile,config,parent,dedicated=False):
    parent=Path(parent).resolve(strict=True)
    root=Path(tempfile.mkdtemp(prefix='instruction-handoff-',dir=parent));root.chmod(0o700)
    work=root/'session';work.mkdir(mode=0o700)
    candidate=root/'config.toml';candidate.write_bytes(Path(config).read_bytes())
    request={'task_id':'TASK-instruction-fixture','objective':'Fixture objective '+'A'*10000+' final 🚀',
             'allowed_paths':['fixture.txt'],'validation_argv':['/usr/bin/true']}
    local('manual_runner').configure_instructions(root,request,python,candidate)
    expected=tomllib.loads(candidate.read_text())['developer_instructions']
    env=dict(os.environ);cwd=Path.cwd()
    try:
        session=local('probe_live_session').probe(source,binary,candidate,work,os.getuid(),expected,exercise_project_trust=True)
    finally:
        os.environ.clear();os.environ.update(env);os.chdir(cwd)
    # No inference is implemented by the session probe: initialize/thread/start/config/read only.
    if not session['success']:raise RuntimeError('no-turn native instruction check failed; retain evidence')
    workers=local('probe_manual_runner').run(source,python,profile,config,root,dedicated)
    result={'scope':'native-instruction-handoff-model-free','success':session['success'] and workers['success'],
            'uid':os.getuid(),'api_calls':0,'inference_requests':0,'real_credentials_used':False,
            'dedicated_cgroup_tested':dedicated,'session':session,'workers':workers,'installed_services_modified':False}
    (root/'evidence.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'success':result['success'],'evidence':str(root/'evidence.json'),'api_calls':0}))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source','python','binary','profile','config','parent'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--dedicated-cgroup',action='store_true')
    args=parser.parse_args()
    result=run(args.source,args.python,args.binary,args.profile,args.config,args.parent,args.dedicated_cgroup)
    raise SystemExit(0 if result['success'] else 1)
