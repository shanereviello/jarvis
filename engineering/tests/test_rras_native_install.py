import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('installer',Path(__file__).resolve().parents[1]/'tools/rras_native/install_host_review.py')
i=importlib.util.module_from_spec(spec);spec.loader.exec_module(i)


class InstallerTests(unittest.TestCase):
    def fixture(self,root):
        review=root/'review';review.mkdir()
        for n,data in [('build-tools/uv',b'fixture uv'),('profile/config.yaml',b'{}'),('codex/config.toml',b'')]:
            p=review/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
        with tarfile.open(review/'hermes-source.tar.gz','w:gz') as t:
            data=b'fixture project';item=tarfile.TarInfo('pyproject.toml');item.size=len(data);t.addfile(item,io.BytesIO(data))
        files={str(p.relative_to(review)):hashlib.sha256(p.read_bytes()).hexdigest() for p in review.rglob('*') if p.is_file()}
        (review/'manifest.json').write_text(json.dumps({'files':files}))
        return review,hashlib.sha256((review/'manifest.json').read_bytes()).hexdigest()

    def test_manifest_and_inventory_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            r,h=self.fixture(Path(tmp));i.verify_review(r,h)
            with self.assertRaises(ValueError):i.verify_review(r,'wrong')
            (r/'extra').write_text('unexpected')
            with self.assertRaises(ValueError):i.verify_review(r,h)
            (r/'extra').unlink();(r/'profile/config.yaml').write_text('tampered')
            with self.assertRaises(ValueError):i.verify_review(r,h)

    def test_links_rejected_even_when_target_bytes_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);r,h=self.fixture(root)
            target=root/'target';target.write_bytes(b'{}');(r/'profile/config.yaml').unlink();(r/'profile/config.yaml').symlink_to(target)
            with self.assertRaises(ValueError):i.verify_review(r,h)

    def test_runtime_pin_and_link_escape_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);runtime=root/'runtime';(runtime/'bin').mkdir(parents=True)
            binary=runtime/'bin/python3.13';binary.write_bytes(b'fixture interpreter')
            pin={'version':'3.13.16','artifact_sha256':'f4b1bfb3c79b5bb11b8d228a12504163b4c0dab4d679828d8f5f26b6cb6ab35d','executable_sha256':hashlib.sha256(binary.read_bytes()).hexdigest()}
            (runtime/'runtime-pin.json').write_text(json.dumps(pin))
            with patch.object(i,'trusted',side_effect=lambda p:Path(p).resolve()):
                self.assertEqual(i.verify_python(binary),binary)
                pin['executable_sha256']='wrong';(runtime/'runtime-pin.json').write_text(json.dumps(pin))
                with self.assertRaises(ValueError):i.verify_python(binary)
                pin['executable_sha256']=hashlib.sha256(binary.read_bytes()).hexdigest();(runtime/'runtime-pin.json').write_text(json.dumps(pin))
                outside=root/'outside';outside.write_text('fixture');(runtime/'escape').symlink_to(outside)
                with self.assertRaises(ValueError):i.verify_python(binary)

    def simulate(self,failed=False,state_exists=False):
        # All operations are ordinary-user writes in TemporaryDirectory. Root/account,
        # trusted-chain and dependency build calls are explicitly substituted.
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);root=Path(temp.name)
        review,pin=self.fixture(root);base=root/'opt';state=root/'state'
        if state_exists:state.mkdir();(state/'existing-record').write_text('preserve')
        def build(*args,**kwargs):
            self.assertIn('--frozen',args[0]);self.assertIn('--no-dev',args[0]);self.assertNotIn('--no-editable',args[0])
            if failed:raise RuntimeError('fixture dependency failure')
            v=base/'releases/native-06/venv';(v/'bin').mkdir(parents=True);(v/'bin/hermes').write_text('fixture executable');(v/'bin/hermes').chmod(0o755);(v/'pyvenv.cfg').write_text('fixture')
        with patch.object(i,'BASE',base),patch.object(i,'STATE',state),patch.object(i,'UV_SHA',hashlib.sha256(b'fixture uv').hexdigest()),patch.object(i.os,'geteuid',return_value=0),patch.object(i,'trusted',side_effect=lambda p:Path(p).resolve()),patch.object(i,'verify_python',side_effect=lambda p:Path(p)),patch.object(i,'account',return_value=SimpleNamespace(pw_uid=os.getuid(),pw_gid=os.getgid())),patch.object(i.os,'chown'),patch.object(i.subprocess,'check_output',return_value='3.13.16\n'),patch.object(i.subprocess,'run',side_effect=build) as runner:
            if failed or state_exists:
                with self.assertRaises((ValueError,RuntimeError)):i.install(review,pin,root,'native-06')
            else:
                e=i.install(review,pin,root,'native-06');self.assertEqual(e['phase'],'installed-disabled');self.assertFalse(e['services_installed']);self.assertEqual(e['tasks_run'],0)
                self.assertTrue((state/'profiles/rras-engineering/config.yaml').exists())
                self.assertEqual((state.stat().st_mode & 0o777),0o700)
                self.assertEqual(((base/'releases/native-06/venv/bin/hermes').stat().st_mode & 0o222),0)
            if state_exists:self.assertFalse(runner.called);self.assertEqual((state/'existing-record').read_text(),'preserve');self.assertFalse(base.exists())
            if failed:
                e=json.loads((base/'releases/native-06/installation-result.json').read_text());self.assertEqual(e['phase'],'failed');self.assertFalse(state.exists())

    def test_preserves_existing_state_before_mutation(self):self.simulate(state_exists=True)
    def test_failed_build_retains_receipt_and_no_runtime_state(self):self.simulate(failed=True)
    def test_fresh_disabled_release_simulated(self):self.simulate()


if __name__=='__main__':unittest.main()
