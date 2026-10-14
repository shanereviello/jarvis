"""Model-free native runtime check, intended only for an isolated disposable image."""
import hashlib
import json
import os
from pathlib import Path
import sys


def write_passed(exists, exit_code, allowed, execution_verified):
    """A denial is evidence only after admitted commands actually execute."""
    return exists is allowed and ((exit_code == 0) is allowed) and (allowed or execution_verified)


def run():
    evidence = {"schema_version": 1, "scope": "disposable-native-container",
                "inference_requests": 0, "real_environment_helper": True,
                "full_dispatch_tested": False, "success": False, "cases": []}
    root = Path("/fixture")
    profile, board, workspace, sibling = (root / p for p in
        ("profile", "profile/kanban", "profile/workspaces/task", "profile/workspaces/sibling"))
    for p in (profile, board, workspace, sibling):
        p.mkdir(mode=0o700, parents=True, exist_ok=True)
    home = profile / "codex"
    home.mkdir(mode=0o700)
    config = Path("/opt/rras-native-review/codex/config.toml").read_text()
    (home / "config.toml").write_text(config + '\n[analytics]\nenabled=false\n')
    os.environ.update({"HOME": str(profile), "HERMES_HOME": str(profile), "CODEX_HOME": str(home),
                       "HERMES_KANBAN_TASK": "fixture-task", "HERMES_KANBAN_DB": str(board / "kanban.db"),
                       "HERMES_KANBAN_WORKSPACES_ROOT": str(workspace.parent),
                       "GITHUB_TOKEN": "RRAS_NON_SECRET_FILTER_TEST_SENTINEL"})
    sys.path.insert(0, "/opt/hermes")
    client = None
    try:
        from tools.environments.local import hermes_subprocess_env
        from agent.transports.codex_app_server import CodexAppServerClient
        env = hermes_subprocess_env(inherit_credentials=True)
        evidence["cases"].append({"name": "real_helper_isolated_home", "passed": env.get("CODEX_HOME") == str(home)})
        evidence["cases"].append({"name": "synthetic_unrelated_token_stripped", "passed": "GITHUB_TOKEN" not in env})
        source = Path("/opt/hermes/agent/transports/codex_app_server.py")
        evidence["source_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
        if evidence["source_sha256"] != "1bd7e181aa18e7a1417708ed8b691f3523657096d4fae51a268d8fa6d7afca57":
            raise ValueError("native source changed")
        os.chdir(workspace)
        client = CodexAppServerClient(codex_bin="/opt/rras-codex/bin/codex", codex_home=str(home))
        reply = client.initialize(client_name="rras_container_probe", client_version="1")
        evidence["cases"].append({"name": "native_initialize", "passed": True})
        evidence["cases"].append({"name": "reported_isolated_home", "passed": reply.get("codexHome") == str(home)})
        execution_verified = True
        for name, target, allowed in (("task_write", workspace / "probe", True),
                                     ("board_write", board / "probe", True),
                                     ("sibling_write_denied", sibling / "probe", False)):
            result = client.request("command/exec", {"command": ["/bin/sh", "-c", 'printf probe > "$1"', "probe", str(target)],
                "cwd": str(workspace), "timeoutMs": 5000}, timeout=15)
            passed = write_passed(target.exists(), result["exitCode"], allowed, execution_verified)
            if allowed:
                execution_verified = execution_verified and passed
            evidence["cases"].append({"name": name, "passed": passed, "exit_code": result["exitCode"],
                                      "stderr_tail": result.get("stderr", "")[-2048:]})
        evidence["success"] = all(c["passed"] for c in evidence["cases"])
    except Exception as exc:
        evidence["error"] = type(exc).__name__ + ": " + str(exc)
    finally:
        if client:
            evidence["native_stderr_tail"] = client.stderr_tail(5)
            client.close()
    return evidence


if __name__ == "__main__":
    result = run()
    print(json.dumps(result))
    raise SystemExit(0 if result["success"] else 1)
