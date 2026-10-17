"""Exact two-link canary validation; no ROS, network or model operations."""
import json
from pathlib import Path
import subprocess

BASELINE='8465684a2f7ded018b777c2d6f34fa89ecb7898c'
REPLACEMENTS={
 'docs/interfaces/README.md':(
  'Use the interface template in `docs/templates/interface.md` for future additions.',
  'Use the [interface template](../templates/interface.md) for future additions.',
  'docs/templates/interface.md'),
 'docs/procedures/README.md':(
  'Use `docs/templates/procedure.md` for future procedure records.',
  'Use the [procedure template](../templates/procedure.md) for future procedure records.',
  'docs/templates/procedure.md'),
}


def git(root,*args):
    return subprocess.run(['/usr/bin/git','-c','safe.directory='+str(root),'-c','core.hooksPath=/dev/null',
        '-c','core.fsmonitor=false','-C',str(root),*args],env={'PATH':'/usr/bin:/bin','HOME':'/nonexistent',
        'GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null','GIT_OPTIONAL_LOCKS':'0'},
        stdin=subprocess.DEVNULL,capture_output=True,check=True,timeout=15).stdout


def regular(root,name):
    p=root/name
    if any(x.is_symlink() for x in (p,*p.parents)) or not p.is_file() or p.stat().st_size>131072:
        raise ValueError('bounded regular document required')
    return p


def validate(root,expected_baseline=BASELINE):
    root=Path(root).resolve(strict=True)
    if git(root,'rev-parse','HEAD').decode().strip()!=expected_baseline:raise ValueError('canary baseline changed')
    changed=set(filter(None,(git(root,'diff','--no-renames','--name-only','-z',expected_baseline,'--')+
        git(root,'ls-files','--others','--exclude-standard','-z')).decode().split('\0')))
    if changed!=set(REPLACEMENTS):raise ValueError('exact two-file change required')
    for name,(old,new,target) in REPLACEMENTS.items():
        original=git(root,'show',expected_baseline+':'+name)
        if original.count(old.encode())!=1:raise ValueError('baseline sentence mismatch')
        if regular(root,name).read_bytes()!=original.replace(old.encode(),new.encode()):
            raise ValueError('changes differ from exact approved replacement')
        regular(root,target)
    return {'scope':'mk1-template-navigation-canary','success':True,'baseline':expected_baseline,
            'changed_paths':sorted(changed),'exact_replacements':2,'relative_links_checked':2,'runtime_tested':False}


if __name__=='__main__':
    try:print(json.dumps(validate(Path.cwd())))
    except Exception as exc:
        print(json.dumps({'success':False,'error_type':type(exc).__name__}));raise SystemExit(1)
