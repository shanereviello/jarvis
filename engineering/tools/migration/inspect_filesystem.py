"""Read-only migration inventory. Emit path references and deployment metadata, never secrets."""
import argparse
import json
import os
import socket
from pathlib import Path
import subprocess

TARGETS=('/srv/hermes-dev','/srv/jarvis-codex','/srv/jarvis-activity','/opt/jarvis','/opt/hermes','/opt/rras-engineering','/srv/backups','/opt/jarvis-codex','/var/lib/jarvis-codex')
EXCLUDE={'secrets','credentials','.aws','.codex','.agents','.git','__pycache__','node_modules','venv','.venv','runtime','data','logs','cache'}
EXTENSIONS={'.py','.sh','.service','.timer','.conf','.yaml','.yml','.toml'}


def references(roots,limit=10000):
    rows=[];unreadable=[];examined=0
    for root in map(Path,roots):
        if not root.exists():continue
        if root.is_symlink():continue
        candidates=[]
        if root.is_file():candidates=[root]
        else:
            def onerror(e):unreadable.append(str(e.filename))
            for parent,dirs,files in os.walk(root,followlinks=False,onerror=onerror):
                dirs[:]=[d for d in dirs if d not in EXCLUDE and not (Path(parent)/d).is_symlink()]
                for n in files:
                    p=Path(parent)/n
                    # Cron entries and custom shell launchers may have no suffix.
                    if p.suffix in EXTENSIONS or (not p.suffix and not n.startswith('.')):candidates.append(p)
        for p in candidates:
            if p.is_symlink() or p.name=='.env' or p.name.startswith('.env.') or any(x in EXCLUDE for x in p.parts):continue
            if any(x in p.name.lower() for x in ('secret','password','credential','token','private_key','auth.json')):continue
            examined+=1
            if examined>limit:raise ValueError('inventory limit exceeded; narrow roots')
            try:
                if not p.is_file() or p.stat().st_size>4*1024*1024:continue
                text=p.read_text(errors='replace')
            except OSError:unreadable.append(str(p));continue
            counts={target:text.count(target) for target in TARGETS if target in text}
            if counts:rows.append({'source_file':str(p),'path_reference_counts':counts})
    return {'files_examined':examined,'references':rows,'unreadable_paths':sorted(set(unreadable))}


def containers():
    ids=subprocess.check_output(['docker','ps','-aq'],timeout=15).decode().split()
    if not ids:return []
    data=json.loads(subprocess.check_output(['docker','inspect',*ids],timeout=30));rows=[]
    for c in data:
        labels=c.get('Config',{}).get('Labels') or {}
        rows.append({'name':c['Name'],'state':c['State']['Status'],'image_configuration_id':c['Image'],
          'project':labels.get('com.docker.compose.project'),'service':labels.get('com.docker.compose.service'),
          'compose_files':labels.get('com.docker.compose.project.config_files'),
          'mounts':[{'type':m['Type'],'source':m['Source'],'destination':m['Destination'],'rw':m['RW']} for m in c['Mounts']],
          'networks':{n:{'aliases':v.get('Aliases')} for n,v in c['NetworkSettings']['Networks'].items()},
          'published_ports':c['NetworkSettings'].get('Ports'),'health':c['State'].get('Health',{}).get('Status')})
    return rows


def main():
    if socket.gethostname().split('.')[0]!='server01':raise SystemExit('server01 required')
    if os.geteuid()!=0:raise SystemExit('Administrator read access required; no host changes performed')
    roots=['/etc/systemd/system','/etc/cron.d','/etc/cron.daily','/etc/cron.weekly','/etc/cron.monthly','/etc/crontab',
           '/var/spool/cron/crontabs','/root/.config/systemd/user','/home/shanereviello/.config/systemd/user',
           '/opt/hermes','/opt/jarvis/app','/opt/jarvis/scripts','/opt/jarvis/compose.yml','/opt/jarvis-codex-review-v2',
           '/srv/hermes-dev/jarvis/runner','/srv/hermes-dev/robot_ws/runner']
    result={'scope':'filesystem-migration-read-only-inventory','schema_version':1,'source_scan':references(roots),
            'containers':containers(),'host_changes':False,'secret_values_printed':False}
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
