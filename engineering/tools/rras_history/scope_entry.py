"""Installed scope CLI bootstrap. Never migrates implicitly."""
import importlib.util
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'vendor'))

if __name__=='__main__':
    spec=importlib.util.spec_from_file_location('installed_scope_cli',Path(__file__).with_name('scope_cli.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);module.main()
