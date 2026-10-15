import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch,Mock

spec=importlib.util.spec_from_file_location('worker_wait',Path(__file__).resolve().parents[1]/'tools/rras_native/wait_worker.py')
w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)


class WaitTests(unittest.TestCase):
    def test_foreign_pid_never_adopted(self):
        with self.assertRaises(ValueError):w.NativeChild(os.getpid())

    def test_native_pid_handle_preserves_exit_status(self):
        p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(.2);raise SystemExit(7)'])
        self.addCleanup(p.wait)
        h=w.NativeChild(p.pid)
        e=w.wait_worker(h,lambda:'running',lambda:[],2)
        self.assertEqual(e['exit_code'],7)
        self.assertFalse(e['success'])

    def test_done_does_not_ignore_remaining_descendant(self):
        p=Mock(pid=123,poll=Mock(return_value=0))
        with patch.object(w,'identity',return_value={'ppid':os.getpid(),'start_ticks':1}):
            e=w.wait_worker(p,lambda:'done',lambda:[456],.01)
        self.assertEqual(e['outcome'],'timeout')
        self.assertFalse(e['worker_stop_verified'])
        p.terminate.assert_not_called()
        p.kill.assert_not_called()

    def test_pid_reuse_fails_closed(self):
        p=Mock(pid=123,poll=Mock(return_value=None))
        with patch.object(w,'identity',side_effect=[{'ppid':os.getpid(),'start_ticks':1},{'ppid':os.getpid(),'start_ticks':2}]):
            e=w.wait_worker(p,lambda:'done',lambda:[],1)
        self.assertEqual(e['outcome'],'identity_ambiguous')
        self.assertFalse(e['worker_stop_verified'])

    def test_unbounded_wait_refused(self):
        for t in (0,601):
            with self.assertRaises(ValueError):w.wait_worker(Mock(),lambda:'done',lambda:[],t)
