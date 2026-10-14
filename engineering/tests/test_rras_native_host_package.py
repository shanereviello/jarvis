"""Pinned host packaging without the retired container topology."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]/'tools/rras_native'
def load(name):
    s=importlib.util.spec_from_file_location(name,ROOT/(name+'.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
runtime=load('package_host_runtime');host=load('prepare_host')

class HostPackageTests(unittest.TestCase):
    def fixture(self,root):
        binary=root/'bin/codex';binary.parent.mkdir();binary.write_bytes(b'fixture-cli')
        for name in ('bin/codex-code-mode-host','codex-resources/bwrap','codex-resources/zsh/bin/zsh','codex-path/rg'):
            p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'fixture-resource')
        return binary
    def test_wrong_pin_refused_before_destination_creation(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);binary=self.fixture(root)
            with self.assertRaises(ValueError):runtime.prepare(root/'review','candidate-model',binary)
            self.assertFalse((root/'review').exists())
    def test_missing_resources_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);binary=self.fixture(root);(root/'codex-resources/bwrap').unlink()
            with patch.object(runtime,'OBSERVED_LOCAL_CLI_SHA256',hashlib.sha256(binary.read_bytes()).hexdigest()):
                with self.assertRaises(ValueError):runtime.prepare(root/'review','candidate-model',binary)
            self.assertFalse((root/'review').exists())
    def test_host_manifest_resources_and_no_container_artifacts(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);binary=self.fixture(root);target=root/'review'
            with patch.object(runtime,'OBSERVED_LOCAL_CLI_SHA256',hashlib.sha256(binary.read_bytes()).hexdigest()):
                manifest=runtime.prepare(target,'candidate-model',binary)
            for name,h in manifest['files'].items():self.assertEqual(hashlib.sha256((target/name).read_bytes()).hexdigest(),h)
            self.assertFalse((target/'Dockerfile').exists());self.assertFalse(list(target.glob('container_*.py')))
            self.assertTrue((target/'runtime/codex-resources/bwrap').exists())
            self.assertEqual(json.loads((target/'activation-plan.json').read_text())['target'],'dedicated-low-privilege-host')
            with self.assertRaises(ValueError):runtime.prepare(target,'candidate-model',binary)
    def test_host_source_revision_and_checksum_refused(self):
        with patch.object(host,'git',return_value=b'wrong'):
            with self.assertRaises(ValueError):host.verify_source('fixture')
        with patch.object(host,'git',side_effect=[host.REVISION.encode(),b'wrong']):
            with self.assertRaises(ValueError):host.verify_source('fixture')
