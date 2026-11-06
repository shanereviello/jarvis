"""Pinned project CLI bootstrap; does not select a transport or upgrade a store."""
import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'vendor'))


def main():
    spec = importlib.util.spec_from_file_location('installed_project_cli', Path(__file__).with_name('project_cli.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.main()


if __name__ == '__main__':
    main()
