"""Pinned offline dependency bootstrap; run only from an immutable release with -I -B."""
import importlib.util
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[3]


def main(argv=None):
    if sys.version_info[:3]!=(3,13,16):raise SystemExit('Dashboard interpreter version refused.')
    sys.path.insert(0,str(ROOT/'vendor'))
    spec=importlib.util.spec_from_file_location('protected_history_web_entry',Path(__file__).with_name('entry.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);module.main(argv)


if __name__=='__main__':main()
