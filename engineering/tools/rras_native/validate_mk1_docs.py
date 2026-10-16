"""Phase-1 documentation acceptance; stdlib only, no ROS/build/runtime calls."""
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote,urlsplit

BASELINE='45ef5e00326fce4274084e0ca00c2240f7b18baf'
REQUIRED=[
 'docs/README.md','docs/00-system-overview.md','docs/architecture/README.md','docs/architecture/mk1-system-context.md',
 'docs/ros/README.md','docs/ros/packages/roboclaw-driver.md','docs/ros/nodes/roboclaw.md',
 'docs/interfaces/README.md','docs/hardware/README.md','docs/hardware/roboclaw.md',
 'docs/hosts/README.md','docs/hosts/raspberry-pi.md','docs/procedures/README.md','docs/decisions/README.md',
 'docs/observations/README.md','docs/assets/README.md',
 *['docs/templates/'+name+'.md' for name in ('ros-package','ros-node','hardware-component','host','interface','procedure','architecture-decision-record')]]


def git(root,*args):
    env={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','LANG':'C.UTF-8','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null','GIT_OPTIONAL_LOCKS':'0'}
    return subprocess.run(['/usr/bin/git','-c','core.hooksPath=/dev/null','-c','core.fsmonitor=false','-C',str(root),*args],env=env,stdin=subprocess.DEVNULL,capture_output=True,check=True,timeout=15).stdout


def validate(root,expected_baseline=BASELINE):
    root=Path(root).resolve(strict=True)
    if git(root,'rev-parse','HEAD').decode().strip()!=expected_baseline:raise ValueError('documentation baseline changed')
    changed=set(filter(None,(git(root,'diff','HEAD','--name-only','-z')+git(root,'ls-files','--others','--exclude-standard','-z')).decode().split('\0')))
    if not changed<=set(REQUIRED):raise ValueError('changes outside documentation contract')
    ids={};links=0
    for name in REQUIRED:
        p=root/name
        if any(x.is_symlink() for x in (p,*p.parents)) or not p.is_file() or p.stat().st_size>128*1024:raise ValueError('regular bounded documentation file required: '+name)
        text=p.read_text(encoding='utf-8')
        if not text.startswith('---\n') or '\n---\n' not in text[4:]:raise ValueError('frontmatter required: '+name)
        header,body=text[4:].split('\n---\n',1)
        pairs=re.findall(r'^([a-z_]+):[^\S\n]*([^\n]*)$',header,re.M)
        fields=dict(pairs)
        if len(fields)!=len(pairs):raise ValueError('duplicate frontmatter field: '+name)
        if not {'id','title','kind','system','status','last_verified','source_refs'}<=fields.keys():raise ValueError('metadata fields missing: '+name)
        identifier=fields['id'].strip('\'"')
        if not re.fullmatch('[a-z0-9][a-z0-9_.-]{2,159}',identifier) or identifier in ids:raise ValueError('invalid or duplicate documentation ID')
        ids[identifier]=name
        if fields['status'].strip('\'"') not in ('draft','reviewed','verified','deprecated'):raise ValueError('invalid documentation status')
        if fields['status'].strip('\'"')=='verified':raise ValueError('initial documentation must not claim runtime verification')
        # Skip fenced examples, but check normal Markdown and image destinations.
        visible=re.sub(r'(?ms)^\s*(```|~~~).*?^\s*\1\s*$', '', body)
        for target in re.findall(r'!?\[[^\]\n]*\]\(([^\n)]+)\)',visible):
            target=target.split(' "',1)[0].strip().strip('<>')
            if target.startswith('#'):continue
            url=urlsplit(target)
            if url.scheme in ('http','https','mailto'):continue
            if url.scheme or target.startswith('/'):raise ValueError('relative repository links required: '+name)
            path=unquote(url.path)
            resolved=(p.parent/path).resolve()
            if not resolved.is_relative_to(root) or not resolved.exists():raise ValueError('unresolved repository link: '+name+' -> '+target)
            links+=1
        if re.search(r'\b(?:sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{20,}|PLACEHOLDER_SECRET|FAKE_API_KEY)\b',text):raise ValueError('secret-like placeholder or credential refused')
    return {'scope':'mk1-phase1-documentation','success':True,'documents':len(ids),'relative_links_checked':links,
            'changed_paths':sorted(changed),'baseline':expected_baseline,'runtime_tested':False}

if __name__=='__main__':
    try:print(json.dumps(validate(Path.cwd())))
    except Exception as e:print(json.dumps({'success':False,'error_type':type(e).__name__,'detail':str(e)}));raise SystemExit(1)
