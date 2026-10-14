"""Run harmless wait/cgroup cases; no Hermes board, credentials or inference."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

spec=importlib.util.spec_from_file_location('wait_worker',Path(__file__).with_name('wait_worker.py'))
w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)


def run(root, dedicated):
    root=Path(root).resolve(strict=True)
    if root.stat().st_uid!=os.getuid() or root.stat().st_mode & 0o077:
        raise ValueError('private fixture required')
    if dedicated and w.cgroup_peers():
        raise ValueError('dedicated cgroup is not initially empty')
    cases=[]
    for name,code,native,timeout in (
        ('done_before_exit','import time;time.sleep(.4)','done',2),
        ('crash','import time;time.sleep(.1);raise SystemExit(7)','running',2),
        ('exit_without_completion','import time;time.sleep(.1)','running',2),
        ('timeout','import time;time.sleep(10)','running',.2),
    ):
        p=subprocess.Popen([sys.executable,'-I','-B','-c',code],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        started=time.monotonic()
        peers=w.cgroup_peers if dedicated else lambda: [p.pid] if p.poll() is None else []
        try:
            result=w.wait_worker(p,lambda:native,peers,timeout)
            elapsed=time.monotonic()-started
            expected={'done_before_exit':'completed','crash':'failed','exit_without_completion':'failed','timeout':'timeout'}[name]
            passed=result['outcome']==expected and (name!='done_before_exit' or elapsed>=.35)
            cases.append({'name':name,'passed':passed,'result':result,'elapsed':elapsed})
            with (root/(name+'.json')).open('x') as f:json.dump(cases[-1],f,indent=2)
        finally:
            # Exact fixture Popen handle, not planned names or retained PID adoption.
            if p.poll() is None:p.terminate()
            p.wait(timeout=3)
    if dedicated:
        # Leader exits while an actual same-cgroup descendant remains.
        marker=root/'descendant.pid'
        code='import subprocess,time;from pathlib import Path;p=subprocess.Popen(['+repr(sys.executable)+',"-I","-B","-c","import time;time.sleep(1.0)"]);Path('+repr(str(marker))+').write_text(str(p.pid));time.sleep(.15)'
        p=subprocess.Popen([sys.executable,'-I','-B','-c',code],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        result=w.wait_worker(p,lambda:'done',w.cgroup_peers,.5)
        cases.append({'name':'descendant_prevents_verified_stop','passed':result['outcome']=='timeout' and not result['worker_stop_verified'],'result':result})
        p.wait(timeout=3)
        deadline=time.monotonic()+3
        while w.cgroup_peers() and time.monotonic()<deadline:time.sleep(.05)
        if w.cgroup_peers():raise RuntimeError('fixture descendant still live; retain unit')
    result={'scope':'manual-waiter-model-free','uid':os.getuid(),'dedicated_cgroup_tested':dedicated,'api_calls':0,'success':all(c['passed'] for c in cases),'cases':cases}
    with (root/'evidence.json').open('x') as f:json.dump(result,f,indent=2)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--work',required=True);p.add_argument('--dedicated-cgroup',action='store_true')
    a=p.parse_args();r=run(a.work,a.dedicated_cgroup);print(json.dumps(r));sys.exit(0 if r['success'] else 1)
