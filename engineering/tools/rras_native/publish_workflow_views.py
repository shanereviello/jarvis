"""Publish a bounded sanitized generation and atomically switch only its index.

No daemon, model, ledger, private-data mount or authority mutation. Superseded
pages remain immutable snapshots. The reader sees either complete index version.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import uuid
import fcntl


def local(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def publish(store, directory, reader_gid):
    j, a = local('workflow_journal'), local('activity')
    directory = Path(directory)
    if type(reader_gid) is not int or reader_gid < 0:
        raise ValueError('reader group required')
    if not directory.is_absolute() or directory.resolve(strict=True) != directory or not directory.is_dir():
        raise ValueError('existing absolute projection directory required')
    info = directory.stat()
    if info.st_uid != os.getuid() or info.st_gid != reader_gid or stat.S_IMODE(info.st_mode) != 0o750:
        raise ValueError('caller-owned reader-group 0750 directory required')
    root = Path(store)
    if root == directory or root in directory.parents or directory in root.parents:
        raise ValueError('private store and public projections must be separate trees')
    journal = j.Journal(root)
    # Lock is in the private store, never exposed through the reader mount.
    lock_path = root / 'projection-publish.lock'
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'rb') as lock:
        if lock_path.stat().st_uid != os.getuid() or stat.S_IMODE(lock_path.stat().st_mode) != 0o600:
            raise ValueError('private publisher lock required')
        fcntl.flock(lock, fcntl.LOCK_EX)
        index = directory / 'index.json'
        if index.exists() or index.is_symlink():
            if index.is_symlink() or index.stat().st_uid != os.getuid() or index.stat().st_nlink != 1:
                raise ValueError('owned projection index required')
            local('workflow_read_tools').pages(directory)
        rows = journal.records()  # One immutable in-memory snapshot for every page.
        work_ids = sorted({row['work_item_id'] for row, _ in rows if row['kind'] == 'work_item'})
        generation = 'g' + uuid.uuid4().hex
        entries = []
        with tempfile.TemporaryDirectory(prefix='.projection-build-', dir=root.parent) as temporary:
            stage = Path(temporary)
            for work_id in work_ids:
                after = 0
                while True:
                    if len(entries) >= 256:
                        raise ValueError('projection generation exceeds 256 pages')
                    name = generation + '-' + work_id + '-' + str(after) + '.json'
                    result = journal.publish_jarvis(stage / name, work_id, after=after, _snapshot=rows)
                    view = j.read_projection(stage / name)
                    entries.append({'work_item_id': work_id, 'after': after, 'file': name})
                    if not result['has_more']:
                        break
                    after = view['summary']['next_after']
            raw_index = j.encoded({'schema_version': 1, 'pages': entries})
            # Copy finalized private-stage files to unique public names. Existing
            # index still points exclusively to the previous generation.
            for entry in entries:
                source = stage / entry['file']
                destination = directory / entry['file']
                with destination.open('xb') as output:
                    os.fchmod(output.fileno(), 0o440)
                    os.fchown(output.fileno(), os.getuid(), reader_gid)
                    output.write(source.read_bytes()); output.flush(); os.fsync(output.fileno())
            a.fsync_directory(directory)
            # The temporary index must be on the destination filesystem.
            index_fd, temporary_index = tempfile.mkstemp(prefix='.index-', dir=directory)
            try:
                with os.fdopen(index_fd, 'wb') as stream:
                    os.fchmod(stream.fileno(), 0o440)
                    os.fchown(stream.fileno(), os.getuid(), reader_gid)
                    stream.write(raw_index); stream.flush(); os.fsync(stream.fileno())
                os.replace(temporary_index, index)
                a.fsync_directory(directory)
            finally:
                Path(temporary_index).unlink(missing_ok=True)
        return {'generation': generation, 'work_items': len(work_ids), 'pages': len(entries),
                'index_sha256': j.digest(raw_index), 'execution_authorized': False}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('store', 'directory'):
        p.add_argument('--' + name, required=True)
    p.add_argument('--reader-gid', type=int, required=True)
    args = p.parse_args(argv)
    print(json.dumps(publish(args.store, args.directory, args.reader_gid)))


if __name__ == '__main__':
    main()
