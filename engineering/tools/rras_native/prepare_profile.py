"""Prepare an absent-only, credential-free native profile review candidate."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil


def prepare(destination, model):
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("destination must be absent")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", model):
        raise ValueError("explicit model identifier required")
    # JSON is valid YAML: avoid a new YAML dependency in this small packaging tool.
    config = {"model": {"provider": "openai-api", "default": model,
                        "api_mode": "codex_app_server",
                        "openai_runtime": "codex_app_server"},
              "approvals": {"mode": "manual"},
              "agent": {"disabled_toolsets": ["bfl"]},
              "security": {"tirith_enabled": False},
              "platform_toolsets": {"cli": ["kanban", "skills"]}}
    files = {
        "profile/config.yaml": json.dumps(config, indent=2) + "\n",
        "codex/config.toml": (
            f'model = "{model}"\nmodel_provider = "rras-api"\n'
            'sandbox_mode = "workspace-write"\napproval_policy = "on-request"\n'
            '[sandbox_workspace_write]\nnetwork_access = false\n'
            'exclude_slash_tmp = true\nexclude_tmpdir_env_var = true\n'
            '[model_providers.rras-api]\nname = "RRAS API Platform"\n'
            'base_url = "https://api.openai.com/v1"\nenv_key = "RRAS_OPENAI_API_KEY"\n'
            'wire_api = "responses"\n'),
        "activation-plan.json": json.dumps({
            "schema_version": 1, "status": "uninstalled-review-candidate",
            "profile": "rras-engineering", "model": model,
            "model_entitlement_verified": False, "codex_cli_candidate": "0.159.0",
            "codex_artifact_sha256": None, "codex_artifact_included": False,
            "hermes_image_configuration_id": "sha256:b99f4564d5e17ec0183314c0d2f6f633657cff4916fad0f05f6e7667722da432",
            "launch_environment": {"HERMES_HOME": "/opt/data/profiles/rras-engineering",
                                   "CODEX_HOME": "/opt/data/profiles/rras-engineering/codex",
                                   "HERMES_KANBAN_WORKSPACES_ROOT": "/opt/data/profiles/rras-engineering/workspaces"},
            "credential_source": "pending-explicit-provisioning;not-copied",
            "budget_policy": "operator-api-portal;custom-enforcement-deferred",
            "unattended_execution_enabled": False,
            "gates": ["review persistent image build and executable checksum",
                      "validate isolated home propagation in native dispatcher",
                      "validate callback toolsets and approval behavior",
                      "register native project and canonical repository mapping",
                      "model-free protocol/worktree/handoff checks"]}, indent=2) + "\n",
    }
    destination.mkdir(mode=0o700, parents=True)
    for name, text in files.items():
        path = destination / name
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        path.write_text(text)
        path.chmod(0o600)
    source = Path(__file__).with_name("activity.py")
    shutil.copyfile(source, destination / "activity.py")
    (destination / "activity.py").chmod(0o600)
    manifest = {"schema_version": 1, "files": {
        str(p.relative_to(destination)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(destination.rglob("*")) if p.is_file()}}
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (destination / "manifest.json").chmod(0o600)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--model", required=True, help="Explicit candidate; no entitlement check or API call")
    args = parser.parse_args()
    prepare(args.destination, args.model)
    print(args.destination)


if __name__ == "__main__":
    main()
