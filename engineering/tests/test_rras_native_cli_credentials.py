"""Refusal checks for the sentinel-only native CLI construction fixture."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('cli_fixture',ROOT/'tools/rras_native/probe_cli_credentials.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class CredentialFixtureTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)

    def test_accepts_only_exact_harmless_fixture(self):
        p=self.root/'credential';p.write_bytes(m.SENTINEL)
        self.assertEqual(m.read_fixture(p),'RRAS-NONSECRET-OFFLINE-FIXTURE')
        p.write_bytes(b'x'*len(m.SENTINEL))
        with self.assertRaises(ValueError):m.read_fixture(p)

    def test_symlink_and_directory_refused(self):
        p=self.root/'credential';p.write_bytes(m.SENTINEL)
        link=self.root/'link';link.symlink_to(p)
        for path in (link,self.root):
            with self.assertRaises(ValueError):m.read_fixture(path)

    def test_wrong_uid_refuses_before_fixture_changes(self):
        with self.assertRaises(ValueError):
            m.probe('/absent','/absent',self.root,'/absent',os.getuid()+1)
        self.assertEqual(list(self.root.iterdir()),[])

    def test_inherited_credential_environment_refused(self):
        with patch.dict(os.environ,{'OPENAI_API_KEY':'not-a-real-key'},clear=True):
            with self.assertRaises(ValueError):
                m.probe('/absent','/absent',self.root,'/absent',os.getuid())
        self.assertEqual(list(self.root.iterdir()),[])

    def test_nonprivate_work_refused(self):
        self.root.chmod(0o755)
        with self.assertRaises(ValueError):
            m.probe('/absent','/absent',self.root,'/absent',os.getuid())
        self.assertEqual(list(self.root.iterdir()),[])

    def test_generated_systemd_argv_preserves_runtime_credential_expansion(self):
        import subprocess
        script=(ROOT/'tools/rras_native/run_cli_credential_acceptance.sh').read_text()
        command=script.split('sudo systemd-run --unit',1)[1].split('2>&1 |',1)[0]
        fixture='''set -eu
UNIT=fixture
ACCOUNT=fixture
WORK=/fixture/work
SOURCE_ROOT=/fixture/source
RELEASE=/fixture/release
REVIEW=/fixture/review
sudo() { printf '%s\\0' "$@"; }
'''
        args=subprocess.check_output(['bash','-c',fixture+'sudo systemd-run --unit'+command]).decode().split('\0')
        self.assertIn('CREDENTIALS_DIRECTORY=${CREDENTIALS_DIRECTORY}',args)
        self.assertEqual(args[args.index('--credential')+1],'${CREDENTIALS_DIRECTORY}/rras-fixture')
        self.assertFalse(any('%d' in a for a in args))
        self.assertIn('LoadCredential=rras-fixture:/fixture/source/fixture',args)
