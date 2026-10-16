"""Cross-UID operator handoff acceptance, confined to a local bare remote."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import pwd
import re


def local(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def fixture_root(root):
    root=Path(root)
    if root.parent!=Path('/var/lib') or not re.fullmatch('rras-publication-operator-[0-9a-f]{32}',root.name):raise ValueError('exact disposable fixture root required')
    return root


def prepare(root,source):
    if os.geteuid()!=0:raise ValueError('administrator setup required')
    root=fixture_root(root);source=Path(source)
    if source.parent!=Path('/var/lib') or not re.fullmatch('rras-publication-workflow-[0-9a-f]{32}',source.name):raise ValueError('prior workflow fixture required')
    custody=local('publication_custody');a=local('activity');handoff=local('publication_handoff')
    previous=json.loads(custody.root_bytes(source/'acceptance.json',1024*1024))
    if previous['scope']!='publication-custody-to-local-git-model-free' or previous['success'] is not True or previous['github_tested'] is not False or previous['network_used'] is not False:
        raise ValueError('successful local fixture acceptance required')
    local('approved_launch').trusted(root.parent)
    root.mkdir(mode=0o755);root.chmod(0o755)
    control=root/'control';control.mkdir(mode=0o700)
    remote=root/'remote.git';handoff.git(['init','--bare','--quiet',str(remote)])
    operator=pwd.getpwnam('shanereviello')
    if operator.pw_uid in (0,996,997):raise ValueError('separate operator identity required')
    for p in [remote,*remote.rglob('*')]:os.chown(p,operator.pw_uid,operator.pw_gid,follow_symlinks=False)
    policy=json.loads(custody.root_bytes(source/'fixture-policy.json',1024*1024))
    policy['repositories']['jarvis']['remote']=str(remote)
    a.absent(control/'fixture-policy.json',a.encoded(policy))
    custody.prepare(source/'custody',control/'fixture-policy.json',control/'publication')
    handoff.export(control/'publication.prepared.json',control/'fixture-policy.json',root/'handoff')
    return {'scope':'operator-handoff-local-fixture-prepared','root':str(root),'github_tested':False,'api_calls':0}


def check(root,workspace):
    root=fixture_root(root);handoff=local('publication_handoff');a=local('activity')
    record,_=handoff.read(root/'handoff')
    if record['prepared']['remote']!=str(root/'remote.git'):raise ValueError('only fixture local transport allowed')
    prepared=handoff.import_review(root/'handoff',workspace)
    result=handoff.publish(root/'handoff',workspace)
    evidence={'scope':'root-to-operator-local-publication','success':result['status']=='published',
              'operator_uid':os.getuid(),'api_calls':0,'real_credentials_used':False,'worker_launched':False,
              'github_tested':False,'network_used':False,'installed_services_modified':False,
              'cases':['root_reviewed_bundle_read','operator_owned_checkout','exact_local_branch_push','publication_receipt'],
              'commit':prepared['commit'],'branch':prepared['branch']}
    a.absent(Path(workspace)/'acceptance.json',a.encoded(evidence))
    return evidence

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--action',choices=('prepare','check'),required=True)
    p.add_argument('--root',required=True);p.add_argument('--source');p.add_argument('--workspace');args=p.parse_args()
    result=prepare(args.root,args.source) if args.action=='prepare' else check(args.root,args.workspace)
    print(json.dumps(result));raise SystemExit(0 if result.get('success',True) else 1)
