"""Worker rejection stages expose no request contents or credentials."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import pytest


def test_worker_diagnostics_preserve_checks_without_sensitive_logging():
    root=Path(__file__).resolve().parents[1]
    node=shutil.which('node')
    if node is None:
        spec=importlib.util.find_spec('playwright')
        if spec:node=str(Path(spec.origin).parent/'driver/node')
    if not node:pytest.skip('reviewed Node runtime required')
    result=subprocess.run([node,str(root/'tests/codex_edge_diagnostics.js'),
        str(root/'tools/rras_reporting/codex_edge_worker.mjs')],text=True,capture_output=True,timeout=15,check=True)
    assert json.loads(result.stdout)==dict(signature_mismatch=True,scope_rejections=True,upstream_status=True,
        no_sensitive_logs=True,security_checks_preserved=True)
