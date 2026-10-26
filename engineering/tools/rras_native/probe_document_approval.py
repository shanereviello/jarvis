"""Fixed model-free protected-document host fixture entrypoint."""
import importlib.util
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[3]
STATE=Path('/var/lib/rras-document-approval-acceptance-20261025')
sys.path.insert(0,str(ROOT/'vendor'))


def run():
    path=Path(__file__).with_name('probe_workflow_host.py')
    spec=importlib.util.spec_from_file_location('document_workflow_fixture',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.run(STATE,document_bound=True)


if __name__=='__main__':
    print(json.dumps(run()))
