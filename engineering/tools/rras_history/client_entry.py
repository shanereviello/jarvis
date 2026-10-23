"""Pinned runtime client bootstrap; explicit interactive configuration stays fixed."""
import importlib.util
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'vendor'))


def main():
    path=Path(__file__).with_name('interactive_cli.py')
    spec=importlib.util.spec_from_file_location('history_installed_client',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);module.main()


if __name__=='__main__':main()
