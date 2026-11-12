"""Unix transport for a configured planning broker; no registration API."""
import importlib.util
import os
from pathlib import Path


def unix():
    path=Path(__file__).resolve().parent.parent/'rras_history'/'unix.py'
    spec=importlib.util.spec_from_file_location('onboarding_broker_unix_transport',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def server(path,broker,on_bound=None):
    u=unix()
    if not hasattr(broker,'dispatch') or type(getattr(broker,'grants',None)) is not dict or not broker.grants:
        raise ValueError('configured planning broker required')
    class PlanningServer(u.Server):
        def __init__(self):
            u.uid(os.getuid())
            if os.geteuid()!=os.getuid():raise ValueError('unprivileged service required')
            self.path=u.endpoint(path);self.access=broker
            self.listener=None;self.identity=None;self.on_bound=on_bound
    return PlanningServer()
