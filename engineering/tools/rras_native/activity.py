"""Single-operator native task admission/evidence CLI; no task execution or API calls."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


class RecordError(ValueError):
    pass


def encoded(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                       separators=(",", ":")) + "\n").encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", value):
        raise RecordError("invalid identifier")
    return value


def load(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise RecordError("duplicate JSON key")
            result[key] = value
        return result
    path = Path(path)
    if path.is_symlink() or path.stat().st_size > 1024 * 1024:
        raise RecordError("invalid or oversized record")
    return json.loads(path.read_bytes(), object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(RecordError("invalid JSON number")))


def fsync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def absent(path, data):
    path = Path(path)
    if path.is_symlink():
        raise RecordError("record symlink")
    try:
        with path.open("xb") as stream:
            os.chmod(path, 0o600)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        if path.read_bytes() != data:
            raise RecordError("existing record conflicts; preserve it") from None
    fsync_directory(path.parent)


def git(repo, *args):
    env = {"PATH": os.defpath, "HOME": "/nonexistent", "LANG": "C.UTF-8",
           "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
           "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0"}
    result = subprocess.run(["git", "-c", "safe.directory=" + str(Path(repo).resolve()), "-c", "core.fsmonitor=false", "-c",
                             "core.hooksPath=/dev/null", "-C", str(repo), *args],
                            env=env, stdin=subprocess.DEVNULL, capture_output=True, timeout=30)
    if result.returncode:
        raise RecordError("Git inspection failed")
    if len(result.stdout) > 8 * 1024 * 1024:
        raise RecordError("Git evidence exceeds 8 MiB")
    return result.stdout


def canonical_repo(path):
    path = Path(path).resolve(strict=True)
    root = Path(git(path, "rev-parse", "--show-toplevel").decode().strip()).resolve()
    if root != path:
        raise RecordError("repository path must be the repository root")
    return root


def private_dir(path):
    path = Path(path)
    if path.is_symlink():
        raise RecordError("state directory symlink")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.stat()
    if info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise RecordError("state directory must be caller-owned 0700")
    return path


def registration(registry, repo_id):
    rows = load(registry)
    if set(rows) != {"schema_version", "repositories"} or rows["schema_version"] != 1:
        raise RecordError("invalid registry schema")
    matches = [r for r in rows["repositories"] if r.get("repository_id") == repo_id]
    if len(matches) != 1:
        raise RecordError("repository not uniquely registered")
    row = matches[0]
    if set(row) != {"repository_id", "path", "enabled", "hermes_project"} or row["enabled"] is not True:
        raise RecordError("repository disabled or invalid")
    identifier(row["repository_id"])
    identifier(row["hermes_project"])
    if str(canonical_repo(row["path"])) != row["path"]:
        raise RecordError("registry path must be canonical")
    return row


def task_path(state, task_id):
    return private_dir(state) / identifier(task_id)


def task(state, task_id):
    return load(task_path(state, task_id) / "task.json")


def admit(state, registry, task_id, repo_id, objective):
    row = registration(registry, repo_id)
    if not objective.strip() or len(objective.encode()) > 16384:
        raise RecordError("objective must be 1..16384 bytes")
    root = private_dir(task_path(state, task_id))
    path = root / "task.json"
    if path.exists():
        existing = load(path)
        if (existing["repository_id"], existing["repository_path"], existing["objective"],
            existing["hermes_project"]) != (repo_id, row["path"], objective, row["hermes_project"]):
            raise RecordError("task identity conflicts")
        return existing
    record = {"schema_version": 1, "task_id": task_id, "repository_id": repo_id,
              "repository_path": row["path"], "hermes_project": row["hermes_project"],
              "baseline_commit": git(row["path"], "rev-parse", "HEAD").decode().strip(),
              "objective": objective, "profile": "rras-engineering",
              "spending_policy": "operator-api-portal;custom-enforcement-deferred"}
    absent(path, encoded(record))
    return record


def preview(state, task_id):
    record = task(state, task_id)
    body = (f"RRAS task: {record['task_id']}\nRepository: {record['repository_id']}\n"
            f"Admitted baseline: {record['baseline_commit']}\n{record['objective']}\n"
            "Local work only. Human review controls publication and deployment.")
    return {"execute": False, "argv": ["hermes", "kanban", "create", record["task_id"],
            "--body", body, "--assignee", record["profile"], "--workspace", "worktree",
            "--project", record["hermes_project"], "--idempotency-key", "rras:" + task_id,
            "--triage"], "environment_requirement": "isolated engineering HERMES_HOME and CODEX_HOME",
            "note": "Verify native project repository mapping before manually creating this triage task."}


def bind(state, task_id, board, hermes_task, run, thread=None):
    task(state, task_id)
    record = {"board": identifier(board), "hermes_task": identifier(hermes_task),
              "hermes_run": identifier(run), "codex_thread": identifier(thread) if thread else None,
              "source": "operator-attested"}
    absent(task_path(state, task_id) / "binding.json", encoded(record))
    return record


def worktree(record, path):
    root = canonical_repo(path)
    registered = canonical_repo(record["repository_path"])
    common = lambda p: git(p, "rev-parse", "--path-format=absolute", "--git-common-dir").strip()
    if common(root) != common(registered):
        raise RecordError("worktree belongs to another repository")
    git(root, "merge-base", "--is-ancestor", record["baseline_commit"], "HEAD")
    return root


def snapshot(record, root):
    head = git(root, "rev-parse", "HEAD").decode().strip()
    patch = git(root, "diff", "--no-ext-diff", "--no-textconv", "--binary",
                record["baseline_commit"], "--")
    status = git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    if git(root, "rev-parse", "HEAD").decode().strip() != head:
        raise RecordError("HEAD changed during export")
    return head, patch, status


def export(state, task_id, path, logs=(), artifacts=()):
    record = task(state, task_id)
    binding = load(task_path(state, task_id) / "binding.json")
    root = worktree(record, path)
    head, patch, status = snapshot(record, root)
    branch = git(root, "symbolic-ref", "--short", "HEAD").decode().strip()
    files = {"changes.patch": patch, "status.porcelain": status,
             "index.patch": git(root, "diff", "--cached", "--no-ext-diff", "--no-textconv", "--binary", "HEAD", "--")}
    for number, path in enumerate(logs):
        p = Path(path)
        if p.is_symlink() or not p.is_file() or p.stat().st_size > 4 * 1024 * 1024:
            raise RecordError("log must be a regular file up to 4 MiB")
        files[f"reported-log-{number}.txt"] = p.read_bytes()
    # The caller attests logs. No subprocess test invocation or recursive file import.
    for number, path in enumerate(artifacts):
        p = Path(path)
        if p.is_symlink() or not p.is_file() or p.stat().st_size > 4 * 1024 * 1024:
            raise RecordError("artifact must be a regular file up to 4 MiB")
        files[f"additional-artifact-{number}.json"] = p.read_bytes()
    manifest = {"schema_version": 1, "task": record, "binding": binding,
                "worktree": str(root), "branch": branch, "head_commit": head,
                "evidence_state": "captured", "logs_state": "reported-unverified",
                "untracked_content": "names only; content not captured",
                "mutable_worktree": True,
                "files": {name: {"sha256": digest(data), "size_bytes": len(data)}
                          for name, data in files.items()}}
    if artifacts:
        manifest["additional_artifacts"] = [f"additional-artifact-{n}.json" for n in range(len(artifacts))]
    content = encoded(manifest)
    export_id = digest(content)
    parent = private_dir(task_path(state, task_id) / "exports")
    destination = parent / export_id
    if destination.is_symlink():
        raise RecordError("export symlink")
    if destination.exists():
        verify_export(destination)
        if (destination / "manifest.json").read_bytes() != content:
            raise RecordError("export conflict")
    else:
        temporary = Path(tempfile.mkdtemp(prefix=".export-", dir=parent))
        try:
            for name, data in files.items():
                absent(temporary / name, data)
            absent(temporary / "manifest.json", content)
            temporary.rename(destination)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
    # Local content-addressed index; durable export is independent of PostgreSQL availability.
    index = private_dir(task_path(state, task_id) / "index")
    absent(index / (export_id + ".json"), encoded({"export_id": export_id,
           "path": str(destination.resolve()), "database_indexed": False}))
    return {"export_id": export_id, "path": str(destination.resolve()), "database_indexed": False}


def verify_export(path):
    path = Path(path)
    manifest = load(path / "manifest.json")
    if digest(encoded(manifest)) != path.name:
        raise RecordError("manifest digest mismatch")
    for name, info in manifest["files"].items():
        if Path(name).name != name or name in {".", ".."}:
            raise RecordError("invalid export filename")
        p = path / name
        if p.is_symlink() or not p.is_file():
            raise RecordError("invalid export file")
        data = p.read_bytes()
        if len(data) != info["size_bytes"] or digest(data) != info["sha256"]:
            raise RecordError("export artifact changed")
    return manifest


def review(state, task_id, export_id, operator, decision):
    if not re.fullmatch(r"[a-f0-9]{64}", export_id):
        raise RecordError("invalid export ID")
    manifest = verify_export(task_path(state, task_id) / "exports" / export_id)
    root = worktree(manifest["task"], manifest["worktree"])
    head, patch, status = snapshot(manifest["task"], root)
    if (head != manifest["head_commit"] or digest(patch) != manifest["files"]["changes.patch"]["sha256"]
            or digest(status) != manifest["files"]["status.porcelain"]["sha256"]):
        raise RecordError("worktree changed since export; export again")
    if decision not in {"accepted", "rejected"}:
        raise RecordError("invalid decision")
    if decision == "accepted" and status:
        raise RecordError("acceptance requires clean committed work; untracked content is not captured")
    receipt = {"task_id": task_id, "export_id": export_id, "head_commit": head,
               "operator": identifier(operator), "decision": decision,
               "identity_assurance": "local-operator-attested", "remote_actions_authorized": False}
    root = private_dir(task_path(state, task_id) / "reviews")
    absent(root / (digest(encoded(receipt)) + ".json"), encoded(receipt))
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", required=True, type=Path)
    sub = parser.add_subparsers(dest="action", required=True)
    a = sub.add_parser("admit")
    a.add_argument("--registry", required=True, type=Path)
    a.add_argument("--task", required=True)
    a.add_argument("--repo", required=True)
    a.add_argument("--objective", required=True)
    a = sub.add_parser("preview")
    a.add_argument("--task", required=True)
    a = sub.add_parser("bind")
    for name in ("task", "board", "hermes-task", "run"):
        a.add_argument("--" + name, required=True)
    a.add_argument("--thread")
    a = sub.add_parser("export")
    a.add_argument("--task", required=True)
    a.add_argument("--worktree", required=True, type=Path)
    a.add_argument("--log", action="append", default=[], type=Path)
    a = sub.add_parser("review")
    for name in ("task", "export-id", "operator"):
        a.add_argument("--" + name, required=True)
    a.add_argument("--decision", choices=("accepted", "rejected"), required=True)
    args = parser.parse_args()
    try:
        if args.action == "admit":
            result = admit(args.state, args.registry, args.task, args.repo, args.objective)
        elif args.action == "preview":
            result = preview(args.state, args.task)
        elif args.action == "bind":
            result = bind(args.state, args.task, args.board, args.hermes_task, args.run, args.thread)
        elif args.action == "export":
            result = export(args.state, args.task, args.worktree, args.log)
        else:
            result = review(args.state, args.task, args.export_id, args.operator, args.decision)
    except (RecordError, OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
        parser.exit(1, f"refused: {type(exc).__name__}\n")
    print(encoded(result).decode(), end="")


if __name__ == "__main__":
    main()
