"""Opt-in Hermes wrapper; paths are fixed by the reviewed container deployment."""
import importlib.util
from pathlib import Path


def register(ctx):
    entry=Path('/opt/rras-engineering-reporting/engineering/tools/rras_reporting/hermes_runtime.py')
    config=Path('/etc/rras-engineering/hermes-reporting/config.json')
    spec=importlib.util.spec_from_file_location('rras_hermes_reporting',entry)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Validate the protected installation before exposing either tool.
    module.Adapter(module.local('protected_config').decode(config,maximum=1024*1024))
    module.register(ctx,config)
    module.start_delivery_worker(config)
