"""Installed Hermes plugin wrapper; root-reviewed release is mounted read-only."""
import importlib.util
from pathlib import Path


def register(ctx):
    path=Path('/opt/rras-history-reporting/engineering/tools/rras_reporting/hermes_runtime.py')
    if path.resolve()!=path or not path.is_file() or path.stat().st_uid!=0 or path.stat().st_mode&0o022:
        raise ValueError('reviewed installed native reporting source required')
    spec=importlib.util.spec_from_file_location('installed_hermes_engineering_reporting',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.register(ctx,'/etc/rras-hermes-reporting/native.json')
