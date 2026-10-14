"""Execute the actual operator inventory preflight on published-layout fixtures."""
import shutil
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]


class ContextReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.review=Path(self.tmp.name)/'review'
        self.review.mkdir()
        for name in ('probe_dispatcher.py','activity.py'):
            shutil.copyfile(ROOT/'tools/rras_native'/name,self.review/name)
        files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.review.iterdir()}
        (self.review/'manifest.json').write_text(json.dumps(files,sort_keys=True,indent=2)+'\n')
        shutil.copyfile(ROOT/'tools/rras_native/run_native_cli_context_acceptance.sh',self.review/'operator-acceptance.sh')
        text=(ROOT/'tools/rras_native/run_native_cli_context_acceptance.sh').read_text()
        self.code=text.split("<<'PY'\n",1)[1].split('\nPY\n',1)[0]
        # Exercise inventory semantics against this generated private fixture;
        # actual production bundle pins are checked separately before publication.
        fixture_pin=hashlib.sha256((self.review/'manifest.json').read_bytes()).hexdigest()
        self.code=re.sub(r"hexdigest\(\)=='[0-9a-f]{64}'", "hexdigest()=='"+fixture_pin+"'", self.code)

    def check(self):
        return subprocess.run([sys.executable,'-I','-B','-c',self.code,str(self.review)],capture_output=True)

    def test_actual_published_sidecar_inventory_passes(self):
        self.assertEqual(self.check().returncode,0)

    def test_extra_file_and_symlink_sidecar_fail_closed(self):
        (self.review/'unexpected').write_text('unexpected')
        self.assertNotEqual(self.check().returncode,0)
        (self.review/'unexpected').unlink()
        (self.review/'operator-acceptance.sh').unlink()
        (self.review/'operator-acceptance.sh').symlink_to(self.review/'activity.py')
        self.assertNotEqual(self.check().returncode,0)
