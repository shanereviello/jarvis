import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('paid_gate',Path(__file__).resolve().parents[1]/'tools/rras_native/credentials.py')
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
