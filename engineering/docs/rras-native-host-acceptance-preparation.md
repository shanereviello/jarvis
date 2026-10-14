# Host acceptance payload and administrator preparation

2026-10-05. Continues [native dispatcher acceptance](rras-native-dispatcher-acceptance.md). All installation, account provisioning, privileged acceptance, credentials and activation remain pending. Existing gateway, release, timer, records and fences are preserved.

## Source completed and validation

Review bundle `/tmp/rras-native-host-review-20261005-05`, manifest SHA-256 `78ff7c9b5a19a1c3789c2d3123ba0427a1907bb5bc0dad8fe086236208ab5da6`.

New `probe_host_worker.py` requires the actual dedicated UID/GID and only its primary group; rejects root, operator 1000, old supervisor 997 and nobody. It requires worker-owned 0700 cwd, checks an operator-created harmless root-owned 0600 sentinel is unreadable, and rejects Docker socket access. It invokes the real App Server command probe without credentials. Identity errors fail before starting Codex. It creates exclusive evidence files and never accesses real secret contents.

Enhanced `probe_codex.py` verifies task **and** board writes, meaningful sibling denial, and network denial against a loopback listener with a positive unsandboxed reachability control. A namespace startup failure cannot satisfy denial. Actual host test: **five cases passed**, using the reviewed Codex bytes and isolated home, no model turn. That was UID 1000, not dedicated-UID acceptance.

`probe_dispatcher.py --hold-for-stop` retains a native fake-child readiness receipt before holding for 60 seconds. This is a bounded cgroup-stop fixture, not a production orchestration loop. Stopping that disposable cgroup must terminate the native detached child. Its board/worktree/logs are retained; never reinterpret its interrupted running task as completed or release production fences.

`probe_foreground.py` runs native `hermes gateway run` with a fresh credential-free home, no configured messaging platforms and no tasks, checking native `gateway_state.json` readiness. Source supports the no-platform path and embedded dispatcher; **runtime readiness is not established**. The initial ten-second attempt was inconclusive; the subsequent 40-second readiness attempt failed and needed SIGKILL after a 15-second SIGTERM grace. A third bounded attempt enabled Python thread-stack diagnostics and also failed readiness/clean shutdown. Its traces are retained at `/tmp/rras-native-foreground-zgt6znd9/gateway.log`; they do not establish the exact blocked coroutine. All receipts/logs remain under `/tmp/rras-native-foreground-*`. No existing gateway was targeted. [Evidence](rras-native-host-acceptance-preparation-evidence.json) retains the failed attempt and successful boundary results.

**25 focused tests pass** (`test_rras_native*.py`), including identity/group refusal and exact PID cleanup. Syntax, bundle inventory and hashes pass. No full legacy suite rerun. Dedicated-UID and systemd checks have not run.

## Concrete next blocker

Do not select/install a production task service until native foreground readiness and clean shutdown are demonstrated, then repeat within a disposable systemd cgroup under the real worker UID. Diagnose the startup/shutdown delay with bounded stack/log instrumentation in another credential-free fixture; do not add a replacement RRAS dispatcher, deprecated forced daemon, broad permissions or gateway credentials to mask it. The missing optional Slack dependency warning does not by itself prove the readiness failure's cause. Production unit/activation instructions are deliberately dependent on this evidence, not invented here.

## Administrator procedure being prepared

The following are concrete **acceptance commands after a separately reviewed installation**, not permission to install or activate now. The reviewed layout must be:

- `/opt/rras-engineering/releases/native-01`: root-owned immutable bundle, `hermes/` extracted from the pinned source archive, `runtime/` Codex resources and **non-editable** `venv/` built at its final path with uv 0.12.23, Python 3.13.16 and frozen core lock. No temporary venv relocation. No new production service required for these tests.
- Dedicated non-login `jarvis-codex-engineering`, unique UID/GID, no supplementary powerful groups. Determine IDs from live account inspection, never hardcode or repurpose existing identities. Root and named profile must be registered explicitly using native semantics before real dispatch.
- `/var/lib/rras-engineering`: worker-owned 0700, protected root-owned ancestors. No `/srv` changes. Root-owned benign cross-UID fixture under `/var/lib/rras-engineering-review-fixtures`, traversable 0711 parent/run directory with a 0600 sentinel; never place it in a worker-writable parent.
- Code/runtime symlinks resolve into verified root-owned paths with no group/other write permissions. The existing Python path may be reused only after administrator verification of its trust/ownership chain; preserve it unchanged. Root copies the reviewed uv client only after checking its recorded pin, then builds the final environment from the exact frozen source. Build credentials are not needed.

Provisioning/install/rollback commands are not final until foreground acceptance passes. A future install must use absent-only review/release/state destinations, retain the old gateway and all previous releases, install no timer, run acceptance before configuring a production unit, and leave any failure disabled. Rollback removes only the new inactive unit/symlink selection and retains failed evidence/state; never recursively delete shared state or alter old services. Exact final unit rollback depends on the selected native foreground runner.

### Read-only bundle check (safe now)

```bash
(
set -euo pipefail
REVIEW=/tmp/rras-native-host-review-20261005-05
python3 -B - "$REVIEW" <<'PY'
import hashlib,json,sys
from pathlib import Path
r=Path(sys.argv[1]);m=r/'manifest.json'
assert hashlib.sha256(m.read_bytes()).hexdigest()=='78ff7c9b5a19a1c3789c2d3123ba0427a1907bb5bc0dad8fe086236208ab5da6'
files=json.loads(m.read_text())['files']
assert {str(p.relative_to(r)) for p in r.rglob('*') if p.is_file() and p!=m}==set(files)
for n,h in files.items():
 p=r/n
 assert not p.is_symlink() and p.resolve().is_relative_to(r)
 assert hashlib.sha256(p.read_bytes()).hexdigest()==h,n
print('Review verified; nothing installed')
PY
)
```

### Dedicated-UID acceptance command (future, after preconditions)

All paths are new acceptance-only allocations. Run this block only after the above reviewed account/release and root fixture parent exist; it stops if the current runner/user/layout differ. This uses transient units, does not modify installed units, and never starts production reconciliation.

```bash
(
set -euo pipefail
RELEASE=/opt/rras-engineering/releases/native-01
ACCOUNT=jarvis-codex-engineering
STATE=/var/lib/rras-engineering
ROOT_FIXTURES=/var/lib/rras-engineering-review-fixtures
RUN_ID=$(python3 -I -B -c 'import uuid;print(uuid.uuid4().hex)')
UNIT="rras-host-boundary-$RUN_ID"
WORK="$STATE/acceptance-$RUN_ID"
PROTECTED="$ROOT_FIXTURES/$RUN_ID/sentinel"
WORKER_UID=$(id -u "$ACCOUNT")
WORKER_GID=$(id -g "$ACCOUNT")
# Fail before creating anything if administrator review/install is incomplete.
sudo test -x "$RELEASE/venv/bin/python"
sudo test -x "$RELEASE/runtime/bin/codex"
sudo test -f "$RELEASE/probe_host_worker.py"
sudo test -d "$ROOT_FIXTURES"
sudo test ! -e "$WORK"
sudo test ! -L "$WORK"
sudo test ! -e "$ROOT_FIXTURES/$RUN_ID"
printf 'SAVE acceptance RUN_ID=%s UNIT=%s WORK=%s\n' "$RUN_ID" "$UNIT" "$WORK"
sudo install -d -o "$WORKER_UID" -g "$WORKER_GID" -m 0700 "$WORK"
sudo install -d -o root -g root -m 0711 "$ROOT_FIXTURES/$RUN_ID"
printf 'Harmless RRAS acceptance fixture; no credentials\n' | sudo tee "$PROTECTED" >/dev/null
sudo chmod 0600 "$PROTECTED"
# No IPAddressDeny here: the positive loopback control must be reachable outside
# the Codex sandbox. No model request or credentials exist in this payload.
sudo systemd-run --unit "$UNIT" --service-type=exec --wait --pipe --collect \
  -p "User=$ACCOUNT" -p "Group=$ACCOUNT" -p "WorkingDirectory=$WORK" \
  -p UMask=0077 -p NoNewPrivileges=yes -p 'CapabilityBoundingSet=' \
  -p KillMode=control-group -p RuntimeMaxSec=60 -p TimeoutStopSec=10 \
  -p MemoryMax=1G -p TasksMax=128 -p CPUQuota=100% \
  /usr/bin/env -i PATH=/usr/bin:/bin HOME="$WORK" LANG=C.UTF-8 \
  "$RELEASE/venv/bin/python" -I -B "$RELEASE/probe_host_worker.py" \
  --uid "$WORKER_UID" --gid "$WORKER_GID" --protected-fixture "$PROTECTED" \
  --binary "$RELEASE/runtime/bin/codex" --config-template "$RELEASE/codex/config.toml" \
  --evidence "$WORK/codex-evidence.json"
sudo cat "$WORK/identity-evidence.json" "$WORK/codex-evidence.json"
# Retain WORK and protected fixture for review; do not delete records on failure.
)
```

After a timeout/failure, use the **saved exact unit**, not a wildcard, to inspect and stop it. This separate block defines every variable it uses but intentionally requires the exact saved unit as its argument:

```bash
(
set -euo pipefail
printf 'Paste the saved exact acceptance unit name: '
IFS= read -r UNIT
[[ "$UNIT" =~ ^rras-host-boundary-[a-f0-9]{32}$ ]] || exit 1
sudo systemctl show "$UNIT" -p ActiveState -p SubState -p Result -p ControlGroup
# Stop only after confirming this is the successfully created acceptance unit.
# If creation failed or ownership is ambiguous, inspect and preserve; do not adopt it.
[[ $(sudo systemctl show "$UNIT" -p User --value) == jarvis-codex-engineering ]] || exit 1
sudo systemctl stop "$UNIT"
# A collected unit may already be absent; verify no active cgroup, preserve evidence.
sudo systemctl show "$UNIT" -p ActiveState -p SubState -p ControlGroup
)
```

Supply only a confirmed saved name; there is no placeholder to run. No unit name is currently assigned because privileged acceptance has not run. The cgroup-death fixture commands will be finalized alongside the resolved foreground runner; this packet does not claim that gate passed. Machine-readable records distinguish actual model-free host results, simulated coding-child completion, pending UID/cgroup acceptance and future authenticated canary.

2026-10-05 investigation addendum: [foreground lifecycle checkpoint](rras-native-foreground-lifecycle-investigation.md) supersedes the unresolved-lifecycle blocker above. Host-side readiness/SIGTERM teardown pass; the old probe rejected native external-SIGTERM exit 1 and outer sandbox interference blocked asyncio wakeups. Dedicated-UID acceptance and session/authority checks remain pending. Manual one-pass dispatch is sufficient for the first canary after those gates; unattended ownership is a later milestone. Do not execute installation/canary automatically from this addendum.

Deployment preparation follow-up: [dedicated-UID operator guide](rras-native-dedicated-uid-operator-guide.md) supplies the ordered reviewed installation and model-free acceptance commands. It supersedes the earlier proposed non-editable requirement: pinned Hermes explicitly rejects wheels; native uv installation points at root-owned immutable source instead. No build-guard bypass is used. Earlier bundle paths remain historical; use the latest guide's bundle/hash.
