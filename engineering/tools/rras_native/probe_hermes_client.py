"""Test exact installed Hermes wire-client source against Codex without inference.

The environment helper is replaced by a controlled fixture. This is not full
Hermes dispatch, provider, callback, or real environment-helper acceptance.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import types


SOURCE_SHA256 = "1bd7e181aa18e7a1417708ed8b691f3523657096d4fae51a268d8fa6d7afca57"


def probe(source, binary, output):
    source, binary, output = Path(source), Path(binary).resolve(strict=True), Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError("evidence destination must be absent")
    if hashlib.sha256(source.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise ValueError("upstream source changed; review a new source pin")
    evidence = {"schema_version": 1, "scope": "transplanted-installed-native-wire-client",
                "source_sha256": SOURCE_SHA256, "environment_helper": "controlled-fixture",
                "inference_requests": 0, "full_hermes_dispatch_tested": False,
                "success": False, "cases": []}
    with tempfile.TemporaryDirectory(prefix=".rras-hermes-probe-", dir=Path.cwd()) as tmp:
        root = Path(tmp)
        home, workspace, board, sibling = [root / n for n in ("home", "workspace", "board", "sibling")]
        for p in (home, workspace, board, sibling):
            p.mkdir(mode=0o700)
        (home / "config.toml").write_text('sandbox_mode="workspace-write"\n'
            '[sandbox_workspace_write]\nexclude_slash_tmp=true\nexclude_tmpdir_env_var=true\n'
            '[analytics]\nenabled=false\n')
        env = {"PATH": os.defpath, "HOME": str(home), "CODEX_HOME": str(home),
               "LANG": "C.UTF-8", "HERMES_KANBAN_TASK": "fixture-task",
               "HERMES_KANBAN_DB": str(board / "kanban.db"), "RUST_LOG": "error"}
        stub = types.ModuleType("tools.environments.local")
        stub.hermes_subprocess_env = lambda **kwargs: dict(env)
        old = sys.modules.get(stub.__name__)
        sys.modules[stub.__name__] = stub
        compat = types.ModuleType("hermes_cli._subprocess_compat")
        compat.windows_hide_flags = lambda: 0
        old_compat = sys.modules.get(compat.__name__)
        sys.modules[compat.__name__] = compat
        evidence["platform_helper"] = "linux-no-windows-flags-fixture"
        module_name = "rras_upstream_client_fixture"
        spec = importlib.util.spec_from_file_location(module_name, source)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        client = None
        previous_cwd = Path.cwd()
        try:
            spec.loader.exec_module(module)
            # Native workers start in their workspace; the client inherits cwd.
            os.chdir(workspace)
            client = module.CodexAppServerClient(codex_bin=str(binary), codex_home=str(home))
            reply = client.initialize(client_name="rras_native_fixture", client_version="1")
            evidence["cases"].append({"name": "native_client_initialize", "passed": True})
            if "codexHome" in reply:
                evidence["cases"].append({"name": "isolated_home", "passed": Path(reply["codexHome"]) == home})
            for name, target, allowed in (("workspace_write", workspace / "probe.txt", True),
                                         ("board_root_write", board / "probe.txt", True),
                                         ("sibling_write_denied", sibling / "probe.txt", False)):
                result = client.request("command/exec", {"command": ["/bin/sh", "-c", 'printf probe > "$1"', "probe", str(target)],
                    "cwd": str(workspace), "timeoutMs": 5000}, timeout=20)
                passed = (target.exists() is allowed) and ((result["exitCode"] == 0) is allowed)
                evidence["cases"].append({"name": name, "passed": passed, "exit_code": result["exitCode"]})
            evidence["success"] = all(c["passed"] for c in evidence["cases"])
        except Exception as exc:
            evidence["error"] = type(exc).__name__ + ": " + str(exc)
        finally:
            if client:
                client.close()
            os.chdir(previous_cwd)
            if old is None:
                sys.modules.pop(stub.__name__, None)
            else:
                sys.modules[stub.__name__] = old
            sys.modules.pop(module_name, None)
            if old_compat is None:
                sys.modules.pop(compat.__name__, None)
            else:
                sys.modules[compat.__name__] = old_compat
    with output.open("x") as stream:
        os.chmod(output, 0o600)
        json.dump(evidence, stream, indent=2)
        stream.write("\n")
    return evidence


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--binary", required=True)
    parser.add_argument("--evidence", required=True)
    args = parser.parse_args()
    result = probe(args.source, args.binary, args.evidence)
    print(json.dumps(result))
    raise SystemExit(0 if result["success"] else 1)
