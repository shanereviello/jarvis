"""Stage an inactive MCP release and protected config. Never touches services.

Root invocation is an explicit administrator boundary. On partial failure preserve
the journal and allocations; do not rerun or remove them without inspection.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_regular(path, limit=16 * 1024 * 1024):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError("regular bounded input required")
        data = stream.read(limit + 1)
        if len(data) > limit:
            raise ValueError("input too large")
        return data


def payload(candidate, expected):
    candidate = Path(candidate)
    raw = read_regular(candidate / "release-manifest.json")
    if digest(raw) != expected:
        raise ValueError("candidate manifest changed")
    manifest = json.loads(raw)
    if manifest.get("schema_version") != 1 or manifest.get("service") != "mcp" or manifest.get("activation") is not False:
        raise ValueError("inactive MCP manifest required")
    commit = manifest["source_commit"]
    if len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
        raise ValueError("exact source commit required")
    files = {}
    for name, record in manifest["files"].items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts or name == "release-manifest.json":
            raise ValueError("unsafe release member")
        if record["mode"] not in {"100644", "100755"}:
            raise ValueError("nonregular release member")
        for parent in (candidate, *(candidate / relative).parents):
            if parent.is_symlink():
                raise ValueError("symlink ancestor refused")
        data = read_regular(candidate / relative)
        if digest(data) != record["sha256"]:
            raise ValueError("candidate member changed")
        files[name] = (data, 0o555 if record["mode"] == "100755" else 0o444)
    required = {"Dockerfile", "deploy/mcp/compose.release.yml", "deploy/mcp/requirements.lock"}
    if not required <= files.keys():
        raise ValueError("incomplete MCP candidate")
    files["release-manifest.json"] = (raw, 0o444)
    return commit, files


def protected(path):
    path = Path(path)
    for item in (path, *path.parents):
        info = item.lstat()
        if stat.S_ISLNK(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError("unprotected administrator path")


def directory(path, mode):
    path = Path(path)
    protected(path.parent)
    path.mkdir(mode=mode)
    path.chmod(mode)
    protected(path)


def write(path, data, mode, gid=0):
    path = Path(path)
    protected(path.parent)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    with os.fdopen(descriptor, "wb") as stream:
        os.fchown(stream.fileno(), 0, gid)
        os.fchmod(stream.fileno(), mode)
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def stage(candidate, expected):
    if os.geteuid() != 0:
        raise ValueError("administrator invocation required")
    os.umask(0o077)
    commit, files = payload(candidate, expected)
    release_id = "mcp-" + commit[:12]
    release = Path("/opt/jarvis/releases") / release_id
    journal = Path("/var/lib/jarvis-migration") / release_id
    config = Path("/etc/jarvis")
    parent = Path("/opt/jarvis")
    protected(parent.parent)
    original = parent.lstat()
    if not stat.S_ISDIR(original.st_mode) or original.st_uid not in {0, 1000} or original.st_mode & 0o022:
        raise ValueError("unexpected legacy installation directory")
    # Capture private inputs only in memory; never emit bytes or their hashes.
    runtime = read_regular(parent / ".env")
    bridge = read_regular(Path("/srv/n8n/backups/linear-replacement-2026-10-08/N8N_BRIDGE_SECRET.txt"))
    old_compose = read_regular(parent / "compose.yml")
    for target in [release, journal, config / "mcp", config / "linear"]:
        if target.exists() or target.is_symlink():
            raise ValueError("existing allocation; preserve and inspect")
    for target in [release.parent, journal.parent, config]:
        if target.exists():
            if target == release.parent and original.st_uid != 0:
                raise ValueError("release parent exists below unprotected legacy directory")
            protected(target)
        elif target.is_symlink():
            raise ValueError("symlink allocation refused")
    if not journal.parent.exists():
        directory(journal.parent, 0o700)
    protected(journal.parent)
    lock_fd = os.open(journal.parent / "mcp-stage.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(lock_fd, "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        directory(journal, 0o700)
        header = {"release": str(release), "manifest_sha256": expected,
                  "source_commit": commit, "services_changed": False,
                  "original_parent": {"uid": original.st_uid, "gid": original.st_gid,
                                      "mode": oct(stat.S_IMODE(original.st_mode))}}
        write(journal / "intent.json", (json.dumps(header, indent=2) + "\n").encode(), 0o600)
        write(journal / "rollback-compose.yml", old_compose, 0o600)
        write(journal / "rollback-runtime.env", runtime, 0o600)
        try:
            current = parent.lstat()
            if (current.st_dev, current.st_ino) != (original.st_dev, original.st_ino):
                raise ValueError("legacy parent identity changed")
            # Only this parent directory changes ownership; never recursive.
            os.chown(parent, 0, 0, follow_symlinks=False)
            protected(parent)
            if not release.parent.exists():
                directory(release.parent, 0o755)
            directory(release, 0o755)
            for name, (data, mode) in files.items():
                target = release / name
                for ancestor in reversed(target.parent.relative_to(release).parents):
                    directory_path = release / ancestor
                    if not directory_path.exists():
                        directory(directory_path, 0o755)
                if not target.parent.exists():
                    directory(target.parent, 0o755)
                write(target, data, mode)
            if not config.exists():
                directory(config, 0o700)
            directory(config / "mcp", 0o700)
            directory(config / "linear", 0o700)
            write(config / "mcp/runtime.env", runtime, 0o600)
            # Parent0700 denies host users access; read-only container bind grants
            # the existing primary GID1000 access, without group changes.
            write(config / "linear/n8n_bridge_secret", bridge, 0o440, gid=1000)
            assert read_regular(config / "mcp/runtime.env") == runtime
            assert read_regular(config / "linear/n8n_bridge_secret") == bridge
            for name, (data, mode) in files.items():
                target = release / name
                if read_regular(target) != data or stat.S_IMODE(target.stat().st_mode) != mode:
                    raise ValueError("staged source verification failed")
            write(journal / "complete.json", b'{"stage":"complete","services_changed":false,"private_copies_equal":true}\n', 0o600)
        except BaseException:
            print(json.dumps({"stage": "incomplete", "journal": str(journal),
                              "action": "preserve allocations; do not rerun; administrator inspection required"}))
            raise
    return {"stage": "complete", "release": str(release), "journal": str(journal),
            "services_changed": False, "private_copies_equal": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(stage(args.candidate, args.manifest_sha256)))
    except Exception:
        raise SystemExit("Stage refused or incomplete; preserve existing paths and inspect privately.")


if __name__ == "__main__":
    main()
