"""Build/run exactly owned disposable native runtime fixtures; no installed activation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

BASE = "sha256:b99f4564d5e17ec0183314c0d2f6f633657cff4916fad0f05f6e7667722da432"


def command(*args, timeout=30, check=True):
    result = subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout)
    if check and result.returncode:
        raise RuntimeError(f"{args[0]} operation failed: {result.stderr[-2048:]}")
    return result


def inspect(kind, value):
    return json.loads(command("docker", kind, "inspect", value).stdout)[0]


def verify_candidate(root):
    root = Path(root).resolve(strict=True)
    manifest = json.loads((root / "manifest.json").read_text())
    inventory = {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file() and p.name != "manifest.json"}
    if set(manifest["files"]) != inventory:
        raise ValueError("candidate inventory mismatch")
    for name, expected in manifest["files"].items():
        p = root / name
        if p.is_symlink() or not p.resolve().is_relative_to(root) or hashlib.sha256(p.read_bytes()).hexdigest() != expected:
            raise ValueError("candidate integrity mismatch")
    return hashlib.sha256((root / "manifest.json").read_bytes()).hexdigest()


def create_argv(e):
    return ["docker", "create", "--pull=never", "--name", e["container_name"],
            "--label", "rras.native.run=" + e["run_id"], "--label", "rras.native.nonce=" + e["nonce"],
            "--network=none", "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges:true",
            "--memory=512m", "--cpus=1", "--pids-limit=128",
            "--tmpfs", "/fixture:rw,nosuid,nodev,size=32m,mode=0700",
            "--tmpfs", "/tmp:rw,nosuid,nodev,size=32m,mode=1777",
            "--log-driver=local", "--log-opt=max-size=1m", "--log-opt=max-file=1", "--log-opt=compress=false",
            "--entrypoint", "/usr/bin/env", e["image_id"], "-i",
            "PATH=/opt/rras-codex/bin:/opt/rras-codex/codex-path:/usr/local/bin:/usr/bin:/bin",
            "HOME=/fixture/profile", "HERMES_HOME=/fixture/profile", "CODEX_HOME=/fixture/profile/codex",
            "LANG=C.UTF-8", "PYTHONDONTWRITEBYTECODE=1", "/usr/bin/python3", "-B",
            "/opt/rras-native-review/container_probe.py"]


def owned_container(e, info):
    labels = info["Config"].get("Labels") or {}
    return (info["Id"] == e.get("container_id") and info["Image"] == e["image_id"]
            and info["Name"] == "/" + e["container_name"]
            and labels.get("rras.native.run") == e["run_id"]
            and labels.get("rras.native.nonce") == e["nonce"])


def save(root, evidence):
    temp = root / "evidence.next.json"
    temp.write_text(json.dumps(evidence, indent=2) + "\n")
    temp.chmod(0o600)
    temp.replace(root / "evidence.json")


def cleanup(root, e):
    if e.get("creation_status") == "pending-response" or e.get("build_status") == "pending-response":
        raise ValueError("lost operation response; retain resources for exact identity inspection")
    if e.get("container_id") and not e.get("container_removed"):
        info = inspect("container", e["container_id"])
        if not owned_container(e, info):
            raise ValueError("container ownership ambiguous; preserve resources")
        command("docker", "container", "rm", "--force", "--volumes", e["container_id"])
        e["container_removed"] = True
        save(root, e)
    if e.get("image_id") and not e.get("image_tag_removed"):
        info = inspect("image", e["image_tag"])
        labels = info["Config"].get("Labels") or {}
        if info["Id"] != e["image_id"] or labels.get("rras.native.nonce") != e["nonce"]:
            raise ValueError("image ownership ambiguous; preserve image")
        command("docker", "image", "rm", e["image_tag"])
        e["image_tag_removed"] = True
        save(root, e)
    if e.get("base_tag_created") and not e.get("base_tag_removed"):
        if inspect("image", e["base_tag"])["Id"] != BASE:
            raise ValueError("base tag changed; preserve it")
        # Remove only our new tag, never the existing base image by ID.
        command("docker", "image", "rm", e["base_tag"])
        e["base_tag_removed"] = True
        save(root, e)


def run(candidate, run_id):
    if not __import__("re").fullmatch(r"[a-f0-9]{32}", run_id):
        raise ValueError("exact 32-hex run ID required")
    candidate = Path(candidate).resolve(strict=True)
    root = Path("/tmp") / ("rras-native-container-" + run_id)
    root.mkdir(mode=0o700)  # Never resume/overwrite a run.
    e = {"schema_version": 1, "run_id": run_id, "nonce": uuid.uuid4().hex,
         "base_tag": "rras-native-base:" + run_id, "image_tag": "rras-native-review:" + run_id,
         "container_name": "rras-native-probe-" + run_id, "success": False,
         "api_calls": 0, "installed_activation": False}
    save(root, e)
    try:
        e["manifest_sha256"] = verify_candidate(candidate)
        base = inspect("image", BASE)
        if base["Id"] != BASE or (base["Os"], base["Architecture"]) != ("linux", "amd64"):
            raise ValueError("base image identity/platform mismatch")
        existing_tags = command("docker", "image", "ls", "--format", "{{.Repository}}:{{.Tag}}").stdout.splitlines()
        if e["base_tag"] in existing_tags or e["image_tag"] in existing_tags:
            raise ValueError("review image tag already exists")
        names = command("docker", "container", "ls", "--all", "--format", "{{.Names}}").stdout.splitlines()
        if e["container_name"] in names:
            raise ValueError("container name already exists")
        gateway = inspect("container", "hermes")
        e["gateway_before"] = {"id": gateway["Id"], "image": gateway["Image"], "running": gateway["State"]["Running"]}
        command("docker", "image", "tag", BASE, e["base_tag"])
        e["base_tag_created"] = True
        e["build_status"] = "pending-response"
        save(root, e)
        build = command("docker", "build", "--pull=false", "--network=none", "--build-arg", "BASE_IMAGE=" + e["base_tag"],
                        "--label", "rras.native.run=" + run_id, "--label", "rras.native.nonce=" + e["nonce"],
                        "--tag", e["image_tag"], str(candidate), timeout=180, check=False)
        (root / "build.log").write_text(build.stdout + build.stderr)
        e["build_status"] = "confirmed" if build.returncode == 0 else "explicit-failure"
        save(root, e)
        if build.returncode:
            raise RuntimeError("image build failed; inspect retained build.log")
        image = inspect("image", e["image_tag"])
        e["image_id"] = image["Id"]
        save(root, e)
        names = command("docker", "container", "ls", "--all", "--format", "{{.Names}}").stdout.splitlines()
        if e["container_name"] in names:
            raise ValueError("container name appeared before creation; refuse to adopt it")
        e["name_absent_before_create"] = True
        e["creation_status"] = "pending-response"
        save(root, e)
        result = command(*create_argv(e), check=False)
        e["creation_status"] = "confirmed" if result.returncode == 0 else "explicit-failure"
        if result.returncode:
            e["creation_error"] = result.stderr[-2048:]
            save(root, e)
            raise RuntimeError("container creation failed")
        e["container_id"] = result.stdout.strip()
        save(root, e)
        if not owned_container(e, inspect("container", e["container_id"])):
            raise ValueError("created container identity mismatch")
        command("docker", "start", e["container_id"])
        result = command("docker", "wait", e["container_id"], timeout=60)
        e["exit_code"] = int(result.stdout.strip())
        logs = command("docker", "logs", e["container_id"], check=False)
        (root / "probe.log").write_text(logs.stdout + logs.stderr)
        lines = [line for line in logs.stdout.splitlines() if line.startswith('{"schema_version"')]
        if not lines:
            raise RuntimeError("native probe returned no evidence; inspect probe.log")
        e["probe"] = json.loads(lines[-1])
        gateway = inspect("container", "hermes")
        e["gateway_unchanged"] = e["gateway_before"] == {"id": gateway["Id"], "image": gateway["Image"], "running": gateway["State"]["Running"]}
        e["success"] = e["exit_code"] == 0 and e["probe"]["success"] and e["gateway_unchanged"]
    except Exception as exc:
        e["error"] = type(exc).__name__ + ": " + str(exc)
    finally:
        try:
            gateway = inspect("container", "hermes")
            if "gateway_before" in e:
                e["gateway_unchanged"] = e["gateway_before"] == {"id": gateway["Id"], "image": gateway["Image"], "running": gateway["State"]["Running"]}
                if not e["gateway_unchanged"]:
                    e["success"] = False
        except Exception as exc:
            e["gateway_check_error"] = type(exc).__name__
            e["success"] = False
        save(root, e)
        try:
            cleanup(root, e)
        except Exception as exc:
            e["cleanup_error"] = type(exc).__name__ + ": " + str(exc)
            e["success"] = False
        save(root, e)
    return root, e


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--action", choices=("run", "cleanup"), default="run")
    args = parser.parse_args()
    if args.action == "run":
        if not args.candidate:
            parser.error("--candidate required for run")
        root, evidence = run(args.candidate, args.run_id)
    else:
        if not __import__("re").fullmatch(r"[a-f0-9]{32}", args.run_id):
            parser.error("exact run ID required")
        root = Path("/tmp") / ("rras-native-container-" + args.run_id)
        evidence = json.loads((root / "evidence.json").read_text())
        cleanup(root, evidence)
        save(root, evidence)
    print(root / "evidence.json")
    raise SystemExit(0 if args.action == "cleanup" or evidence["success"] else 1)
