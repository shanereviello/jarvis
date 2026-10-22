"""Run an unprivileged passive Unix history service; no installation side effects."""
import argparse
import importlib.util
from pathlib import Path
import signal
import sqlite3
from jsonschema import ValidationError


def local(name):
    spec = importlib.util.spec_from_file_location('history_service_' + name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--socket', required=True)
    parser.add_argument('--store', required=True)
    parser.add_argument('--policy', required=True)
    args = parser.parse_args(argv)
    stopping = False
    def stop(*_):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGTERM, stop); signal.signal(signal.SIGINT, stop)
    try:
        transport = local('unix')
        store = local('store').Store(args.store)
        policy = transport.load_policy(args.policy)
        with transport.Server(args.socket, store, policy) as server:
            while not stopping: server.serve_once()
    except (ValueError, KeyError, TypeError, OSError, sqlite3.Error, ValidationError):
        parser.exit(1, 'History service stopped; preserve store and endpoint evidence.\n')


if __name__ == '__main__': main()
