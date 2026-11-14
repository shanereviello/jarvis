"""Opt-in native Jarvis planning tools with fixed protected configuration."""
import importlib.util
from pathlib import Path


def register(ctx):
    entry=Path('/opt/rras-engineering-reporting/engineering/tools/rras_reporting/hermes_planning.py')
    config=Path('/etc/rras-engineering/hermes-planning/config.json')
    spec=importlib.util.spec_from_file_location('rras_hermes_planning',entry)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.register_configured(ctx,config)
