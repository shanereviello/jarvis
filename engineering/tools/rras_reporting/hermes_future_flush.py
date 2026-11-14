"""Deliver a user-owned Hermes capture spool over the existing scoped socket."""
import importlib.util
import json
from pathlib import Path


def local(name):
    spec = importlib.util.spec_from_file_location('future_flush_' + name, Path(__file__).with_name(name + '.py'))
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value); return value


def main():
    spool = local('capture_intake').Spool('/srv/hermes/data/rras-engineering-capture/spool')
    unix = local('capture_intake').local('unix')
    result = spool.flush(lambda message: unix.call('/run/rras-engineering-history/service.sock', 995, message))
    print(json.dumps(result, allow_nan=False))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit('Hermes capture delivery refused; queued evidence retained.')
