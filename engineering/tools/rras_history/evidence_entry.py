"""Installed evidence CLI bootstrap; no implicit migration or collection."""
import importlib.util
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'vendor'))

if __name__=='__main__':
    spec=importlib.util.spec_from_file_location('installed_evidence_cli',Path(__file__).with_name('evidence_cli.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);value.main()
