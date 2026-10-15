"""Bounded one-pass worker wait; never mutates lifecycle or signals a PID.

Caller must own the child Popen handle and dedicated systemd cgroup. Timeout
retains native writer ownership; the service manager owns verified shutdown.
"""
import os
from pathlib import Path
import time


class NativeChild:
    """Wait handle for a native spawn PID returned directly to this parent.

    No adoption from journals or planned names. Losing wait ownership raises.
    """
    def __init__(self,pid):
        self.pid=pid
        self.returncode=None
        born=identity(pid)
        if born is None or born['ppid']!=os.getpid():
            raise ValueError('native spawn is not a verified direct child')
        self.start_ticks=born['start_ticks']

    def poll(self):
        if self.returncode is None:
            pid,status=os.waitpid(self.pid,os.WNOHANG)
            if pid:
                self.returncode=os.waitstatus_to_exitcode(status)
        return self.returncode


def identity(pid):
    try:
        parts=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()
        return {'ppid':int(parts[1]),'start_ticks':int(parts[19])}
    except FileNotFoundError:
        return None


def cgroup_peers():
    records=Path('/proc/self/cgroup').read_text().splitlines()
    unified=[line.split(':',2)[2] for line in records if line.startswith('0::')]
    if len(unified)!=1:
        raise ValueError('unified dedicated cgroup required')
    relative=unified[0].lstrip('/')
    if not relative or '..' in Path(relative).parts:
        raise ValueError('unsafe cgroup path')
    directory=Path('/sys/fs/cgroup')/relative
    # Include nested cgroups so a child cannot hide by moving below the unit.
    files=[directory/'cgroup.procs',*directory.rglob('*/cgroup.procs')]
    return sorted({int(p) for f in files for p in f.read_text().split()}-{os.getpid()})


def wait_worker(process, status, peers, timeout, interval=0.05):
    if not 0 < timeout <= 600:
        raise ValueError('timeout must be within 600 seconds')
    born=identity(process.pid)
    if born is None or born['ppid']!=os.getpid():
        return {'outcome':'ownership_unverified','success':False,'worker_stop_verified':False}
    deadline=time.monotonic()+timeout
    while True:
        code=process.poll()
        current=identity(process.pid)
        if code is None and (current is None or current['start_ticks']!=born['start_ticks']):
            return {'outcome':'identity_ambiguous','success':False,'worker_stop_verified':False}
        other=peers()
        if code is not None and not other:
            native=status()
            return {'outcome':'completed' if code==0 and native=='done' else 'failed',
                    'success':code==0 and native=='done','exit_code':code,
                    'native_status':native,'worker_stop_verified':True}
        if time.monotonic()>=deadline:
            return {'outcome':'timeout','success':False,'exit_code':code,
                    'native_status':status(),'remaining_pids':other,
                    'worker_stop_verified':False,'lifecycle_mutated':False}
        time.sleep(interval)
