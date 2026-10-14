"""Bounded credential-free native gateway startup; no tasks or messaging config."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time


def process_snapshot(pid):
    try:
        fields=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()
        return {'pid':pid,'parent':int(fields[1]),'state':fields[0],'start_time':int(fields[19])}
    except (FileNotFoundError,PermissionError,IndexError):
        return None


def descendants(pid):
    rows={}
    for item in Path('/proc').iterdir():
        if item.name.isdigit():
            row=process_snapshot(int(item.name))
            if row:rows[row['pid']]=row
    owned=set();parents={pid}
    while True:
        next_ids={k for k,v in rows.items() if v['parent'] in parents and k not in owned}
        if not next_ids:break
        owned.update(next_ids);parents=next_ids
    return [rows[k] for k in sorted(owned)]


def shutdown_accepted(ready, sigterm_sent, exit_code, forced, remaining, shutdown_observed):
    # Pinned Hermes deliberately returns 1 for external SIGTERM to trigger restart.
    return ready and sigterm_sent and shutdown_observed and exit_code in (0,1) and not forced and not remaining


def run(hermes, diagnostic=False):
    root=Path(tempfile.mkdtemp(prefix='rras-native-foreground-'));home=root/'home';home.mkdir(mode=0o700)
    config={'model':{'provider':'custom:rras-api','default':'gpt-5.4','openai_runtime':'codex_app_server'},
      'providers':{'rras-api':{'api':'https://api.openai.com/v1','key_env':'RRAS_OPENAI_API_KEY'}},
      'platforms':{},'kanban':{'dispatch_in_gateway':True,'dispatch_interval_seconds':2,
                              'max_in_progress':1,'max_in_progress_per_profile':1,'max_spawn':1}}
    (home/'config.yaml').write_text(json.dumps(config))
    env={'PATH':'/usr/bin:/bin','HOME':str(home),'HERMES_HOME':str(home),'CODEX_HOME':str(home/'codex'),
       'HERMES_KANBAN_DB':str(home/'kanban/kanban.db'),'HERMES_KANBAN_WORKSPACES_ROOT':str(root/'workspaces'),
       'PYTHONDONTWRITEBYTECODE':'1','LANG':'C.UTF-8'}
    evidence={'api_calls_requested':0,'tasks_submitted':0,'production_modified':False,
              'root':str(root),'ready':False,'success':False,'startup_window_seconds':40,'grace_seconds':15}
    with (root/'gateway.log').open('w') as log:
        argv=[str(hermes),'gateway','run']
        if diagnostic:
            code="import faulthandler,sys;faulthandler.dump_traceback_later(15,repeat=True);sys.argv=['hermes','gateway','run'];from hermes_cli.main import main;main()"
            argv=[str(hermes.parent/'python'),'-B','-c',code]
        p=subprocess.Popen(argv,env=env,cwd=root,stdout=log,stderr=subprocess.STDOUT)
        evidence['pid']=p.pid
        began=time.monotonic()
        owned=[]
        try:
            for _ in range(160):
                status=home/'gateway_state.json'
                if status.exists():
                    data=json.loads(status.read_text());evidence['status']=data
                    if data.get('gateway_state')=='running' and data.get('pid')==p.pid and not data.get('platforms') and data.get('active_agents',0)==0:
                        evidence['ready']=True;evidence['ready_seconds']=time.monotonic()-began
                        # The native running record precedes final cron/startup wiring.
                        time.sleep(2)
                        break
                if p.poll() is not None:break
                time.sleep(.25)
        finally:
            owned=descendants(p.pid)
            evidence['descendants_before_stop']=owned
            stopped_at=time.monotonic()
            evidence['sigterm_sent']=p.poll() is None
            if p.poll() is None:p.terminate()
            try:p.wait(timeout=15)
            except subprocess.TimeoutExpired:
                evidence['sigkill_required']=True;p.kill();p.wait(timeout=5)
            evidence['exit_code']=p.returncode;evidence['stopped']=p.poll() is not None
            evidence['shutdown_seconds']=time.monotonic()-stopped_at
            remaining=[]
            for row in owned:
                now=process_snapshot(row['pid'])
                if now and now['start_time']==row['start_time'] and now['state']!='Z':remaining.append(now)
            evidence['unexpected_remaining_children']=remaining
            log.flush()
            evidence['shutdown_observed']='Shutdown context: signal=SIGTERM' in (root/'gateway.log').read_text()
            evidence['pid_file_removed']=not (home/'gateway.pid').exists()
            evidence['success']=shutdown_accepted(evidence['ready'],evidence['sigterm_sent'],p.returncode,evidence.get('sigkill_required',False),remaining,evidence['shutdown_observed']) and evidence['pid_file_removed']
    (root/'evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
    return root,evidence


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--hermes',type=Path,required=True);p.add_argument('--diagnostic',action='store_true');a=p.parse_args()
    root,e=run(a.hermes,a.diagnostic);print(root/'evidence.json');raise SystemExit(0 if e['success'] else 1)
