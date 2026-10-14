"""Credential-free local App Server initialization and native write-boundary probe."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import queue
import socket
import sys
import subprocess
import tempfile
import threading


def probe(binary, output, config_template=None):
    binary = Path(binary).resolve(strict=True)
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError("evidence destination must be absent")
    evidence = {"schema_version": 1, "scope": "host-native-codex-model-free",
                "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
                "inference_requests": 0, "hermes_dispatch_tested": False, "success": False,
                "cases": []}
    # Codex refuses helper installation when CODEX_HOME is beneath /tmp.
    # Own only a disposable fixture beneath the caller's writable working directory.
    with tempfile.TemporaryDirectory(prefix=".rras-codex-probe-", dir=Path.cwd()) as tmp:
        root = Path(tmp)
        home, workspace, board, sibling = (root / n for n in ("home", "workspace", "board", "sibling"))
        for p in (home, workspace, board, sibling):
            p.mkdir(mode=0o700)
        config = (
            'sandbox_mode = "workspace-write"\napproval_policy = "on-request"\n'
            '[sandbox_workspace_write]\nnetwork_access = false\n'
            'exclude_slash_tmp = true\nexclude_tmpdir_env_var = true\n'
            '[analytics]\nenabled = false\n')
        if config_template is not None:
            data = Path(config_template).read_bytes()
            evidence["configuration_source_sha256"] = hashlib.sha256(data).hexdigest()
            config = data.decode()
            if 'exclude_slash_tmp' not in config:
                config = config.replace('[sandbox_workspace_write]\n',
                    '[sandbox_workspace_write]\nexclude_slash_tmp=true\nexclude_tmpdir_env_var=true\n')
            config += '\n[analytics]\nenabled=false\n'
        (home / "config.toml").write_text(config)
        env = {"PATH": os.defpath, "HOME": str(home), "CODEX_HOME": str(home),
               "LANG": "C.UTF-8", "RUST_LOG": "error"}
        stderr = (root / "stderr.txt").open("w+")
        proc = subprocess.Popen([str(binary), "app-server", "--strict-config", "--listen", "stdio://"],
                                cwd=workspace, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=stderr, text=True)
        messages = queue.Queue()
        def reader():
            try:
                for line in proc.stdout:
                    messages.put(json.loads(line))
            finally:
                messages.put(None)
        worker = threading.Thread(target=reader, daemon=True)
        worker.start()
        sequence = 0
        def send(method, params, request=True):
            nonlocal sequence
            sequence += 1
            body = {"method": method, "params": params}
            if request:
                body["id"] = sequence
            proc.stdin.write(json.dumps(body) + "\n")
            proc.stdin.flush()
            if not request:
                return
            for _ in range(100):
                response = messages.get(timeout=20)
                if response is None:
                    raise RuntimeError("App Server exited")
                if response.get("id") == sequence:
                    if "error" in response:
                        raise RuntimeError("RPC refused: " + json.dumps(response["error"]))
                    return response["result"]
            raise RuntimeError("too many unexpected events")
        try:
            version = subprocess.check_output([str(binary), "--version"], env=env, text=True, timeout=10).strip()
            evidence["version"] = version
            send("initialize", {"clientInfo": {"name": "rras_model_free_probe", "version": "1"}})
            send("initialized", {}, request=False)
            evidence["cases"].append({"name": "initialize", "passed": True})
            policy = {"type": "workspaceWrite", "writableRoots": [str(workspace), str(board)],
                      "networkAccess": False, "excludeSlashTmp": True, "excludeTmpdirEnvVar": True}
            execution_verified = True
            for name, target, should_write in (("workspace_write", workspace / "probe.txt", True),
                                               ("board_write", board / "probe.txt", True),
                                               ("sibling_write_denied", sibling / "probe.txt", False)):
                # Paths originate exclusively from the private disposable fixture.
                result = send("command/exec", {"command": ["/bin/sh", "-c", 'printf probe > "$1"', "probe", str(target)],
                              "cwd": str(workspace), "sandboxPolicy": policy, "timeoutMs": 5000})
                passed = (target.exists() is should_write) and ((result["exitCode"] == 0) is should_write)
                passed = passed and (should_write or execution_verified)
                if should_write:
                    execution_verified = execution_verified and passed
                evidence["cases"].append({"name": name, "passed": passed, "exit_code": result["exitCode"],
                    "stderr_tail": result.get("stderr", "")[-2048:]})
            # Positive loopback control prevents an unavailable endpoint from counting as denial.
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                listener.listen(4)
                address = listener.getsockname()
                with socket.create_connection(address, timeout=2):
                    pass
                network_code = ("import socket,sys\ntry: socket.create_connection(" + repr(address) + ",timeout=2)\n"
                                "except OSError as e:\n print('NETWORK_DENIED' if e.errno in (1,13,101) else 'INCONCLUSIVE');sys.exit(0)\n"
                                "print('NETWORK_ALLOWED')\n")
                result = send("command/exec", {"command": [sys.executable, "-I", "-B", "-c", network_code],
                              "cwd": str(workspace), "sandboxPolicy": policy, "timeoutMs": 5000})
                evidence["cases"].append({"name": "network_denied", "passed": execution_verified and
                    result["exitCode"] == 0 and result.get("stdout", "").strip() == "NETWORK_DENIED",
                    "exit_code": result["exitCode"], "stdout": result.get("stdout", "")[-256:]})
            evidence["success"] = all(c["passed"] for c in evidence["cases"])
        except Exception as exc:
            evidence["error"] = type(exc).__name__ + ": " + str(exc)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
            proc.stdin.close()
            worker.join(timeout=2)
            proc.stdout.close()
            stderr.seek(0)
            evidence["stderr_tail"] = stderr.read()[-4096:]
            stderr.close()
    with output.open("x") as stream:
        os.chmod(output, 0o600)
        json.dump(evidence, stream, indent=2)
        stream.write("\n")
    return evidence


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--config-template")
    args = parser.parse_args()
    result = probe(args.binary, args.evidence, args.config_template)
    print(json.dumps(result))
    raise SystemExit(0 if result["success"] else 1)
