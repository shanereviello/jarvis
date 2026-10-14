import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('paid_gate',Path(__file__).resolve().parents[1]/'tools/rras_native/manual_paid_canary.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class PaidGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.file=self.root/'credential'
        self.file.write_text('RRAS-NONSECRET-OFFLINE-FIXTURE\n');self.file.chmod(0o600)

    def test_private_systemd_fixture_load_without_output(self):
        with patch.dict(os.environ,{'CREDENTIALS_DIRECTORY':str(self.root)},clear=True):
            self.assertEqual(m.delivered_key(self.file),'RRAS-NONSECRET-OFFLINE-FIXTURE')

    def test_missing_delivery_or_wrong_directory_refused(self):
        for directory in (None,str(self.root/'absent')):
            env={} if directory is None else {'CREDENTIALS_DIRECTORY':directory}
            with patch.dict(os.environ,env,clear=True):
                with self.assertRaises(ValueError):m.delivered_key(self.file)

    def test_symlink_public_mode_and_multiline_refused(self):
        link=self.root/'link';link.symlink_to(self.file)
        with patch.dict(os.environ,{'CREDENTIALS_DIRECTORY':str(self.root)},clear=True):
            with self.assertRaises(OSError):m.delivered_key(link)
            self.file.chmod(0o644)
            with self.assertRaises(ValueError):m.delivered_key(self.file)
            self.file.chmod(0o600);self.file.write_text('not a credential')
            with self.assertRaises(ValueError):m.delivered_key(self.file)

    def test_actual_operator_argv_parses_without_missing_required_flags(self):
        import subprocess
        source=Path(__file__).resolve().parents[1]/'tools/rras_native'
        spec=importlib.util.spec_from_file_location('handoff',source/'probe_native_credential_handoff.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        script=(source/'run_canary_sentinel_acceptance.sh').read_text()
        command=script.split('sudo systemd-run --unit',1)[1].split('2>&1 |',1)[0]
        setup='UNIT=test;ACCOUNT=test;WORK=/fixture;SOURCE_ROOT=/source;RELEASE=/release;REVIEW=/review; sudo() { printf "%s\\0" "$@"; }; '
        argv=subprocess.check_output(['bash','-c',setup+'sudo systemd-run --unit'+command]).decode().split('\0')
        args=argv[argv.index('--source'):]
        while args and not args[-1]:args.pop()
        parsed=module.parser().parse_args(args)
        self.assertEqual(parsed.python,'/release/venv/bin/python')
        self.assertTrue(parsed.dedicated_cgroup)
        self.assertEqual(parsed.credential,'${CREDENTIALS_DIRECTORY}/rras-fixture')

    def test_paid_operator_argv_matches_actual_entrypoint_parser(self):
        import argparse
        import subprocess
        import textwrap
        import sys
        source=Path(__file__).resolve().parents[1]/'tools/rras_native'
        script=(source/'run_authorized_paid_canary.sh').read_text()
        command=script.split('sudo systemd-run --unit',1)[1].split('2>&1 |',1)[0]
        setup='UNIT=test;ACCOUNT=test;WORK=/fixture;KEY_SOURCE=/private/source;RELEASE=/release;REVIEW=/review; sudo() { printf "%s\\0" "$@"; }; '
        argv=subprocess.check_output(['bash','-c',setup+'sudo systemd-run --unit'+command]).decode().split('\0')
        args=argv[argv.index('--source'):]
        while args and not args[-1]:args.pop()
        text=(source/'manual_paid_canary.py').read_text()
        code=textwrap.dedent(text.split("if __name__=='__main__':\n",1)[1].split('    if not x.authorize_one_paid_task',1)[0])
        ns={'argparse':argparse}
        with patch.object(sys,'argv',['manual_paid_canary.py',*args]):exec(code,ns)
        self.assertTrue(ns['x'].authorize_one_paid_task)
        self.assertEqual(ns['x'].credential,'${CREDENTIALS_DIRECTORY}/rras-api')
        self.assertFalse(any('PrivateNetwork=yes'==a for a in argv))

    def test_actual_paid_entrypoint_selects_paid_branch(self):
        import argparse
        import contextlib
        import io
        import sys
        import textwrap
        from types import SimpleNamespace
        from unittest.mock import Mock
        source=Path(__file__).resolve().parents[1]/'tools/rras_native/manual_paid_canary.py'
        code=textwrap.dedent(source.read_text().split("if __name__=='__main__':\n",1)[1])
        run=Mock(return_value={'success':True})
        loader=SimpleNamespace(exec_module=lambda module:None)
        ns={'argparse':argparse,'os':os,'Path':Path,'__file__':str(source),
            'sys':sys,'json':__import__('json'),'importlib':__import__('importlib'),
            'delivered_key':lambda path:'RRAS-NONSECRET-OFFLINE-FIXTURE'}
        argv=['paid.py']
        for name in ('source','python','profile','codex-config','work','credential'):
            argv.extend(['--'+name,'/fixture/'+name])
        argv.append('--authorize-one-paid-task')
        with patch.object(sys,'argv',argv),patch.object(os,'getuid',return_value=996),\
             patch('importlib.util.spec_from_file_location',return_value=SimpleNamespace(loader=loader)),\
             patch('importlib.util.module_from_spec',return_value=SimpleNamespace(run=run)),\
             patch.dict(os.environ,{},clear=True),contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as exited:exec(code,ns)
        self.assertEqual(exited.exception.code,0)
        self.assertTrue(run.call_args.kwargs['paid'])
        self.assertEqual(run.call_args.args[4],'paid')
