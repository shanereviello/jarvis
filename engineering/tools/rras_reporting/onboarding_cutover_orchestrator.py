"""Coordinate one protected root and journal-owner cutover, without retries.

This source is inactive until separately installed and configured. A failure
leaves the root host's retained mask and journal state for reconciliation.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import time


def local(name):
    spec = importlib.util.spec_from_file_location('cutover_orchestrator_' + name,Path(__file__).with_name(name+'.py'))
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def run(config_path, config, *, popen=subprocess.Popen, clock=time.monotonic, wait=time.sleep):
    if os.getuid() != 0 or os.geteuid() != 0:
        raise ValueError('protected root orchestrator required')
    c, adapter, _ = local('onboarding_cutover_entry').configuration(config)
    config_path = Path(config_path)
    if not config_path.is_absolute() or config_path.resolve() != config_path:
        raise ValueError('exact protected configuration path required')
    info = config_path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_gid != adapter.pw_gid or
            info.st_nlink != 1 or stat.S_IMODE(info.st_mode) not in (0o440,0o640) or
            local('protected_config').decode(config_path,require_root=True,maximum=8*1024*1024) != config):
        raise ValueError('root-owned journal-readable configuration required')
    socket = Path(c['broker_socket'])
    try:socket.lstat()
    except FileNotFoundError:pass
    else:raise ValueError('existing broker path requires inspection')
    runtime = local('codex_runtime')
    if type(c['transition']) is not dict or set(c['transition']) != {'plan','old','new'}:
        raise ValueError('exact protected transition required')
    plan_sha = hashlib.sha256(runtime.encoded(c['transition']['plan'])).hexdigest()
    folder = Path(__file__).resolve().parent
    env = dict(PATH='/usr/bin:/bin',HOME='/nonexistent',LANG='C.UTF-8')
    root = peer = None
    try:
        root = popen([sys.executable,'-I',str(folder/'onboarding_cutover_entry.py'),'--config',str(config_path)],
                     env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        deadline = clock()+120
        while True:
            if root.poll() is not None:raise ValueError('protected root host stopped before broker became ready')
            try:info = socket.lstat()
            except FileNotFoundError:info = None
            if info is not None:
                if (not stat.S_ISSOCK(info.st_mode) or info.st_uid != 0 or info.st_gid != adapter.pw_gid or
                        stat.S_IMODE(info.st_mode) != 0o660):
                    raise ValueError('unexpected protected broker socket')
                break
            if clock() >= deadline:raise TimeoutError('protected broker did not become ready')
            wait(.1)
        command = ['/usr/bin/setpriv','--reuid='+str(adapter.pw_uid),'--regid='+str(adapter.pw_gid),
            '--clear-groups','--no-new-privs','--bounding-set=-all','--inh-caps=-all','--ambient-caps=-all',
            sys.executable,'-I',str(folder/'onboarding_cutover_peer_entry.py'),'--config',str(config_path)]
        peer = popen(command,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        peer_out,_ = peer.communicate(timeout=600)
        if peer.returncode != 0:raise ValueError('journal-owner cutover failed; inspect retained state')
        root_out,_ = root.communicate(timeout=30)
        if root.returncode != 0:raise ValueError('protected root host failed; inspect retained state')
        a,b = json.loads(peer_out),json.loads(root_out)
        if (a.get('cutover_complete') is not True or b.get('completed') is not True or
                a.get('plan_sha256') != plan_sha or b.get('plan_sha256') != plan_sha or
                a.get('models_started') != 0 or b.get('models_started') != 0 or b.get('runtime_started') is not False):
            raise ValueError('cutover outcome differs; inspect retained state')
        return dict(completed=True,plan_sha256=plan_sha,runtime_started=False,models_started=0,automatic_retry=False)
    finally:
        for process in (peer,root):
            if process is not None and process.poll() is None:
                process.send_signal(signal.SIGTERM)
                try:process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill();process.wait(timeout=10)


def main():
    parser = argparse.ArgumentParser(description=__doc__);parser.add_argument('--config',required=True)
    args = parser.parse_args()
    os.environ.clear();os.environ.update(PATH='/usr/bin:/bin',HOME='/nonexistent',LANG='C.UTF-8');os.umask(0o077)
    try:
        value = local('protected_config').decode(args.config,require_root=True,maximum=8*1024*1024)
        print(json.dumps(run(args.config,value),sort_keys=True))
    except Exception:
        parser.exit(1,'Cutover incomplete or uncertain; retain state and inspect before retry.\n')


if __name__ == '__main__':main()
