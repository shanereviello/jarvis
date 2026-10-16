import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
import yaml

p=Path(__file__).resolve().parents[1]/'tools/rras_native/configure_preparation.py'
s=importlib.util.spec_from_file_location('configure',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class ConfigureTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.config=self.root/'config.yaml';self.original=b'# keep exact rollback bytes\nmodel: existing\nmcp_servers:\n  linear:\n    url: https://example.invalid\n'
        self.config.write_bytes(self.original);self.config.chmod(0o640)
        self.fragment=self.root/'fragment.yaml';self.fragment.write_text('mcp_servers:\n  rras-coding-preparation:\n    command: /reviewed/python\n')
        self.bundle=self.root/'review';self.state=self.root/'proposals'
    def prepare(self):return m.prepare(self.config,self.fragment,self.bundle,self.state,os.getuid(),os.getgid())
    def test_additive_apply_and_exact_rollback_preserve_state(self):
        self.prepare();self.assertEqual(self.config.read_bytes(),self.original);m.stage(self.bundle);m.apply(self.bundle)
        data=yaml.safe_load(self.config.read_bytes());self.assertEqual(data['model'],'existing');self.assertEqual(data['mcp_servers']['linear']['url'],'https://example.invalid')
        (self.state/'receipt.json').write_text('retain evidence');m.rollback(self.bundle)
        self.assertEqual(self.config.read_bytes(),self.original);self.assertEqual(self.config.stat().st_mode&0o777,0o640)
        self.assertEqual((self.state/'receipt.json').read_text(),'retain evidence')
    def test_concurrent_config_change_blocks_apply_and_rollback(self):
        self.prepare();m.stage(self.bundle);self.config.write_text('model: later\n')
        for fn in (m.apply,m.rollback):
            with self.assertRaises(ValueError):fn(self.bundle)
        self.assertEqual(self.config.read_text(),'model: later\n')
    def test_existing_state_and_symlink_config_refused(self):
        self.state.mkdir()
        with self.assertRaises(ValueError):self.prepare()
        self.state.rmdir();link=self.root/'link';link.symlink_to(self.config)
        with self.assertRaises(ValueError):m.prepare(link,self.fragment,self.bundle,self.state)
    def test_changed_candidate_and_replaced_state_refused(self):
        self.prepare();m.stage(self.bundle);self.state.rename(self.root/'retained');self.state.mkdir()
        with self.assertRaises(ValueError):m.apply(self.bundle)
        self.assertEqual(self.config.read_bytes(),self.original)
        (self.bundle/'config.candidate').write_text('tampered')
        with self.assertRaises(ValueError):m.apply(self.bundle)
    def test_existing_tool_and_repeat_publication_refused(self):
        self.prepare()
        with self.assertRaises(FileExistsError):self.prepare()
        m.stage(self.bundle);m.apply(self.bundle)
        with self.assertRaises(ValueError):m.prepare(self.config,self.fragment,self.root/'another',self.root/'unused')
