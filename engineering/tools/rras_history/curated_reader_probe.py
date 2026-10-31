"""Synthetic host seed/withdraw roles using the prior real storage fixture."""
import importlib.util
import json
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'vendor'))
STATE=Path('/var/lib/rras-curated-container-acceptance-attempt04-20261030')
SERVICE=61157


def run(role):
    if os.getuid()!=SERVICE or os.geteuid()!=SERVICE:raise ValueError('fixture owner differs')
    spec=importlib.util.spec_from_file_location('reader_seed',Path(__file__).with_name('curated_host_probe.py'))
    probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)
    probe.STATE=STATE;probe.SERVICE=SERVICE;probe.CATALOG=STATE/'private/catalog'
    if role=='seed':return probe.seed()
    if role=='withdraw':return probe.withdraw()
    raise ValueError('unknown synthetic owner role')


if __name__=='__main__':print(json.dumps(run(sys.argv[1])))
