"""Export inactive service build contexts from a reviewed Git commit.

No Docker calls, installed-path writes, configuration copies or activation.
Destinations are fresh directories; an interrupted export is preserved for review.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess


SELECTIONS = {
    "mcp": ("app/", "tests/", "Dockerfile", "requirements.txt",
            "requirements-dev.txt", "pytest.ini", ".dockerignore", "deploy/mcp/"),
    "hermes": ("deploy/hermes/", "deploy/rras-coding-preparation/"),
    "activity-ledger": ("activity-ledger/",),
}


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout


def package(repo, commit, service, destination):
    repo, destination = Path(repo), Path(destination)
    if service not in SELECTIONS:
        raise ValueError("unknown service")
    # Resolve to an object ID before using the caller's revision in any other call.
    revision = git(repo, "rev-parse", "--verify", "--end-of-options",
                   commit + "^{commit}").decode().strip()
    rows = git(repo, "ls-tree", "-r", "-z", revision).split(b"\0")
    selected = []
    for row in rows:
        if not row:
            continue
        metadata, raw_name = row.split(b"\t", 1)
        mode, kind, object_id = metadata.decode().split()
        name = raw_name.decode("utf-8")
        if not any(name.startswith(p) if p.endswith("/") else name == p
                   for p in SELECTIONS[service]):
            continue
        path = PurePosixPath(name)
        if path.is_absolute() or any(p in {".", ".."} for p in path.parts):
            raise ValueError("unsafe source path")
        if mode not in {"100644", "100755"} or kind != "blob":
            raise ValueError("nonregular release member: " + name)
        if any(p == ".env" or p.startswith(".env.") or p in {"secrets", ".git"}
               for p in path.parts):
            raise ValueError("private configuration member refused: " + name)
        selected.append((name, mode, object_id))
    if not selected:
        raise ValueError("empty release selection")
    # Refuse existing paths, including dangling symlinks. No resume/adoption.
    destination.mkdir(exist_ok=False)
    manifest = {"schema_version": 1, "service": service, "source_commit": revision,
                "activation": False, "files": {}}
    for name, mode, object_id in selected:
        data = git(repo, "cat-file", "blob", object_id)
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(data)
        target.chmod(0o755 if mode == "100755" else 0o644)
        manifest["files"][name] = {"sha256": hashlib.sha256(data).hexdigest(),
                                  "mode": mode}
    encoded = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode()
    with (destination / "release-manifest.json").open("xb") as stream:
        stream.write(encoded)
    return hashlib.sha256(encoded).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--service", choices=SELECTIONS, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    print(package(args.repo, args.commit, args.service, args.destination))


if __name__ == "__main__":
    main()
