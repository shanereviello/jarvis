# Native runtime preparation and model-free checks

Date: 2026-10-05. Status: **persistent image candidate prepared; host/native-wire checks passed; no image built or deployment changed**.

Continues the [step-two implementation](rras-native-step2-implementation.md). Custom hard-budget enforcement stays deferred; portal spending settings remain operator-managed. No credential was read/copied, inference request sent, paid task run, production migration executed, timer enabled or installed service changed.

## Prepared candidate

Directory: `/tmp/rras-native-runtime-review-07wajmap/candidate`.
Manifest SHA-256: `fd9424dfceb7419217396c1bf0f03c3a36be085ff40114866953cde271c5d28f`.

[prepare_runtime.py](../tools/rras_native/prepare_runtime.py) extends the credential-free profile packager with exact observed Codex 0.159.0 executable bytes, code-mode companion, bundled bubblewrap, zsh and ripgrep, preserving their standalone layout. The main executable SHA-256 is `d2752c52353401f7f6efbfcea68796f4f7a3d3e4769f5d1da53fa49d4856b72f`. All shipped files have manifest hashes; image construction also checks the runtime checksum inventory. It copies only named software resources, not the personal Codex home/auth/config. Voice resources are outside this engineering candidate's scope.

Provenance is the existing installed standalone package, not a newly downloaded or registry-verified release. This is a concrete review pin, not an assertion of an official distribution checksum. The installed Hermes transport source is copied and pinned to `1bd7e181aa18e7a1417708ed8b691f3523657096d4fae51a268d8fa6d7afca57` for compatibility fixtures.

Dockerfile installs the runtime under `/opt/rras-codex` in a **new derivative image**, adds its executable paths and inherits the base entrypoint. It does not install profile settings, mount credentials or change the existing container. Profile settings now exclude broad temporary-directory writes using native options. The proposed model remains `gpt-5.4`; account entitlement and inference remain untested.

## Executed checks and findings

| Check | Result | Practical limit |
|---|---|---|
| Focused source tests | **15 passed**, zero failures/errors | Disposable Git/worktree and packaging tests, not the full legacy suite |
| Packaged Codex + candidate configuration | **3 passed**: initialize, workspace write, sibling-write denial | Real host App Server, no inference; analytics disabled in fixture |
| Pinned installed Hermes wire client + packaged Codex | **5 passed**: initialize, isolated home, workspace write, board write, sibling-write denial | Installed client source transplanted to host; controlled environment and Linux helper fixtures; not full dispatcher/provider/callback acceptance |

Real App Server checks follow the [official protocol](https://learn.chatgpt.com/docs/app-server); probes use only initialization and local command execution, never thread turns or login. Machine-readable receipts: [probe evidence](rras-native-step3-probe-evidence.json), `/tmp/rras-native-codex-final-probe-20261005.json`, `/tmp/rras-native-hermes-final-probe-20261005.json`.

Testing exposed and corrected a real packaging defect: copied CLI/companion alone initialized but command execution failed without bundled bubblewrap. The final candidate includes sandbox resources and passes when using its copied executable. A regression now refuses packaging if those resources are missing.

Testing also showed that starting the client in the repository root admits a larger default workspace than intended. Installed native dispatcher source explicitly uses `cwd=workspace`; the corrected fixture matches that behavior and passes sibling denial. This requires correct native launch configuration, not a new custom fence/controller.

The passing fixture places board state and task/sibling workspaces in separate directories. It does **not** prove sibling denial when workspaces are nested beneath the board database directory, because the installed client grants writes to that entire directory. For deployment, use the native `HERMES_KANBAN_WORKSPACES_ROOT` override to place engineering workspaces outside the board directory (proposed `/opt/data/profiles/rras-engineering/workspaces`), and verify the effective board path/roots. This setting is a required follow-up to the current candidate's activation plan, not an already applied configuration. Default board/workspace layout must not be labeled accepted by the separated-directory fixture. One active task remains the initial operating policy.

Earlier failed receipts are preserved: host probe `...-01.json` timed out under the outer restrictions; wire-client `...-01/-02.json` had missing/incorrect fixture helpers; `...-03.json` used the wrong cwd; copied-runtime probes `...candidate-probe...-01/-02.json` lacked sandbox resources. None counts as acceptance. Corrected host/native-client successes apply only to the stated fixture scopes. The CLI logs that system bubblewrap is absent and uses its bundled copy; this fallback was exercised successfully.

## Exact candidate verification

This block reads only the prepared candidate and verifies inventory/hash integrity. Run as the ordinary user:

```bash
(
set -euo pipefail
CANDIDATE=/tmp/rras-native-runtime-review-07wajmap/candidate
python3 -B - "$CANDIDATE" <<'PY'
import hashlib, json, sys
from pathlib import Path
root = Path(sys.argv[1])
manifest = root / 'manifest.json'
assert hashlib.sha256(manifest.read_bytes()).hexdigest() == 'fd9424dfceb7419217396c1bf0f03c3a36be085ff40114866953cde271c5d28f'
entries = json.loads(manifest.read_text())['files']
assert set(entries) == {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and p != manifest}
for name, expected in entries.items():
    p = root / name
    assert not p.is_symlink() and p.resolve().is_relative_to(root.resolve())
    assert hashlib.sha256(p.read_bytes()).hexdigest() == expected
print('Candidate verified; no installation performed')
PY
)
```

The above Python block requires Python 3.9+ for `is_relative_to` (server01 has it). Do not overwrite previous candidates. No runtime credentials belong in this bundle.

## Next deployment slice and remaining gates

Prepare an isolated derivative-image build and **disposable container** acceptance procedure. Verify the exact locally approved Hermes configuration image ID; do not pull a replacement tag. Build into a fresh review image tag and retain its resulting configuration ID. Do not replace/restart the current gateway or enable the profile as part of building an image.

Container validation must then test native initialization, namespace/sandbox availability, board/worktree writes, sibling denial and actual helper/profile environment propagation. Host bubblewrap success does not establish Docker seccomp/user-namespace compatibility. Do not add privileged mode or broad sandbox bypass to make this pass; inspect a concrete failure and make the smallest justified adjustment.

After that, complete actual native triage submission and ID binding, effective callback/tool restrictions and the minimal activity-ledger index. Manual approvals currently remain enabled; unattended Kanban execution must prove its approval behavior rather than silently enabling bypass. A model-backed canary is a separate later operation. No administrator activation command is supplied here because image/container compatibility and profile propagation are still unverified.

Rollback for this completed preparation is simple: none is required for installed services because nothing was installed. Retain the review directories and receipts. A future build/run procedure must own only a fresh image tag, an exact disposable container and its private fixture directory, with exact cleanup and no access to existing runtime fences, gateway state or secrets.
