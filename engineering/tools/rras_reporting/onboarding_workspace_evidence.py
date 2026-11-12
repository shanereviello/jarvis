"""Read-only workspace baseline checks for a protected admission process.

Filesystem and Git inspection alone do not prove process isolation; the caller
must provide a separately trusted, current sandbox isolation verifier. This
module does not create checkouts, grant access, or install runtime policy.
"""
import os
from pathlib import Path
import re
import stat
import subprocess


class Verifier:
    def __init__(self,root,native_uid,socket_for_issue,verify_isolation,git='/usr/bin/git'):
        self.root=Path(root)
        if (not self.root.is_absolute() or self.root.resolve()!=self.root or not self.root.is_dir() or
                type(native_uid) is not int or native_uid<1 or not callable(socket_for_issue) or not callable(verify_isolation) or
                git!='/usr/bin/git'):
            raise ValueError('protected workspace inspection configuration required')
        self.uid,self.socket_for_issue,self.verify_isolation,self.git=native_uid,socket_for_issue,verify_isolation,git

    def __call__(self,value):
        issue=value['issue_id']
        if type(issue) is not str or not re.fullmatch('[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',issue):
            raise ValueError('canonical issue ID required')
        workspace=Path(value['workspace'])
        if (not workspace.is_absolute() or workspace.parent!=self.root or workspace.resolve()!=workspace or
                workspace.name!=issue or value['native_socket']!=self.socket_for_issue(issue)):
            raise ValueError('fixed issue workspace and socket required')
        info=workspace.lstat();gitdir=workspace/'.git'
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid!=self.uid or stat.S_IMODE(info.st_mode)&0o022 or
                not gitdir.is_dir() or gitdir.is_symlink()):
            raise ValueError('private native-owned standalone checkout required')
        env={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null',
             'GIT_TERMINAL_PROMPT':'0','LC_ALL':'C'}
        command=[self.git,'--no-optional-locks','-c','core.hooksPath=/dev/null','-c','core.fsmonitor=false',
                 '-c','safe.directory='+str(workspace),'-C',str(workspace)]
        def run(*args):
            result=subprocess.run([*command,*args],env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20,check=True)
            if len(result.stdout)>65536:raise ValueError('bounded workspace inspection required')
            return result.stdout.decode('utf-8','strict').strip()
        if (run('rev-parse','--show-toplevel')!=str(workspace) or run('rev-parse','HEAD')!=value['baseline_commit'] or
                run('status','--porcelain=v1','--untracked-files=all') or run('remote')):
            raise ValueError('clean fixed-baseline checkout without remotes required')
        if self.verify_isolation(value) is not True:raise ValueError('native sandbox isolation unverified')
        return True
