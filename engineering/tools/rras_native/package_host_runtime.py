"""Package reviewed local executable bytes for a reviewed host runtime candidate."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil


OBSERVED_LOCAL_CLI_SHA256 = "d2752c52353401f7f6efbfcea68796f4f7a3d3e4769f5d1da53fa49d4856b72f"


def prepare(destination, model, binary, hermes_source=None):
    binary = Path(binary).resolve(strict=True)
    if hashlib.sha256(binary.read_bytes()).hexdigest() != OBSERVED_LOCAL_CLI_SHA256:
        raise ValueError("CLI bytes differ from observed 0.159.0 executable; review a new pin")
    companion = binary.with_name("codex-code-mode-host")
    if not companion.is_file() or companion.is_symlink():
        raise ValueError("standalone companion executable unavailable")
    resources = {
        "bin/codex": binary,
        "bin/codex-code-mode-host": companion,
        "codex-resources/bwrap": binary.parent.parent / "codex-resources/bwrap",
        "codex-resources/zsh/bin/zsh": binary.parent.parent / "codex-resources/zsh/bin/zsh",
        "codex-path/rg": binary.parent.parent / "codex-path/rg",
    }
    if any(not p.is_file() or p.is_symlink() for p in resources.values()):
        raise ValueError("standalone sandbox/tool resources unavailable")
    if hermes_source is not None:
        hermes_source = Path(hermes_source)
        if hashlib.sha256(hermes_source.read_bytes()).hexdigest() != "1bd7e181aa18e7a1417708ed8b691f3523657096d4fae51a268d8fa6d7afca57":
            raise ValueError("Hermes transport source differs from inspected image")
    spec = importlib.util.spec_from_file_location("prepare_profile", Path(__file__).with_name("prepare_profile.py"))
    profile = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(profile)
    destination = Path(destination)
    profile.prepare(destination, model)
    runtime = destination / "runtime"
    runtime.mkdir(mode=0o700)
    for name, source in resources.items():
        target = runtime / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        target.chmod(0o555)
    companion_hash = hashlib.sha256(companion.read_bytes()).hexdigest()
    checksums = "".join(f"{hashlib.sha256((runtime/name).read_bytes()).hexdigest()}  {name}\n"
                        for name in resources)
    (destination / "runtime.sha256").write_text(checksums)
    plan = json.loads((destination / "activation-plan.json").read_text())
    plan.update({"codex_artifact_included": True, "codex_artifact_sha256": OBSERVED_LOCAL_CLI_SHA256,
                 "companion_sha256": companion_hash, "provenance": "observed-installed-standalone-package;not-registry-download",
                 "installed": False,
                 "target": "dedicated-low-privilege-host"})
    (destination / "activation-plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    if hermes_source is not None:
        shutil.copyfile(hermes_source, destination / "upstream_codex_app_server.py")
    manifest = {"schema_version": 1, "files": {
        str(p.relative_to(destination)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(destination.rglob("*")) if p.is_file() and p.name != "manifest.json"}}
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--hermes-source", type=Path)
    args = parser.parse_args()
    prepare(args.destination, args.model, args.binary, args.hermes_source)
    print(args.destination)
