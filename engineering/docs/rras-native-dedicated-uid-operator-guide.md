# Dedicated-UID release and model-free acceptance procedure

2026-10-05. **Prepared for administrator review; no administrator operation has been executed by this development pass.** Continues [native lifecycle findings](rras-native-foreground-lifecycle-investigation.md). First canary uses manual one-pass dispatch; unattended Jarvis ownership remains later work. This installs no service/timer, uses no credentials and runs no coding task. Existing `/srv`, Hermes gateway, old `/opt/jarvis-codex` release/runtime, records and fences are untouched.

Candidate `/tmp/rras-native-host-review-20261005-10`;
manifest SHA-256 `abd32ba809820aa061e9f679234df8beabc27178121cf30b2fa472cc8e052275`.
Source checks: **33 focused tests passed**, including simulated installation/failure recovery, runtime pin/link checks, inventory tamper rejection, and machine-readable identity refusal. Actual supported-layout dependency build selected 61 packages; three actual Kanban CLI help checks passed. No root installer or dedicated-UID acceptance has run. [Build evidence](rras-native-dedicated-uid-preparation-evidence.json).

New source: `install_host_review.py` checks trusted ownership chains, full manifest inventory, approved Python runtime pin/tree, pinned uv, unique dedicated UID and no supplementary groups. Release/state are absent-only. Frozen dependencies use the pinned native `uv sync` layout, with source and venv both root-owned and immutable to the worker at their final paths. Failure leaves a read-only installation result and logs; no automatic rollback/adoption. No current-release symlink or units are installed.

Use each complete block separately. Stop on any failed assertion. Do not repeatedly paste a failed block; follow recovery below. Do not repair trust failures by recursively chowning existing trees. Ask for a revised isolated runtime build if the approved existing runtime cannot be verified.

## 1. Read-only preflight and candidate verification

```bash
(
set -euo pipefail
REPO=/srv/hermes-dev/jarvis/tasks/TASK-20260916-001-central-codex-activity-prototype/repo
CANDIDATE=/tmp/rras-native-host-review-20261005-10
ACCOUNT=jarvis-codex-engineering
STATE=/var/lib/rras-engineering
RELEASE=/opt/rras-engineering/releases/native-10
REVIEW=/opt/rras-engineering-review-10
test "$(hostname -s)" = server01
test "$(git -C "$REPO" branch --show-current)" = phase5b/guarded-host-orchestration
test "$(git -C "$REPO" rev-parse HEAD)" = f0d8a6eaf016153708c3e46a32e204a93bd11a97
git -C "$REPO" status --short
test "$(systemctl is-enabled jarvis-codex-reconcile.timer || true)" = disabled
test "$(systemctl is-active jarvis-codex-reconcile.service || true)" = inactive
python3 -I -B - "$CANDIDATE" <<'PY'
import hashlib,json,sys
from pathlib import Path
r=Path(sys.argv[1]);m=r/'manifest.json'
assert hashlib.sha256(m.read_bytes()).hexdigest()=='abd32ba809820aa061e9f679234df8beabc27178121cf30b2fa472cc8e052275'
f=json.loads(m.read_text())['files']
assert {str(p.relative_to(r)) for p in r.rglob('*') if p.is_file() and p!=m}==set(f)
for n,h in f.items():
 p=r/n
 assert not p.is_symlink() and p.resolve().is_relative_to(r)
 assert hashlib.sha256(p.read_bytes()).hexdigest()==h,n
assert not any(p.is_symlink() for p in r.rglob('*'))
print('Reviewed inventory verified')
PY
for DESTINATION in "$STATE" "$RELEASE" "$REVIEW"; do
 sudo test ! -e "$DESTINATION"
 sudo test ! -L "$DESTINATION"
done
if getent passwd "$ACCOUNT" || getent group "$ACCOUNT"; then
 printf 'STOP: existing identity requires review; do not repurpose it.\n'
 exit 1
fi
)
```

Account was absent during source preparation; the live administrator preflight is authoritative. IDs will be allocated by useradd, not guessed from source observations. Preserve all existing changes and installed applications.

## 2. Publish a fresh root-owned reviewed source directory

```bash
(
set -euo pipefail
CANDIDATE=/tmp/rras-native-host-review-20261005-10
REVIEW=/opt/rras-engineering-review-10
sudo test ! -e "$REVIEW"
sudo test ! -L "$REVIEW"
sudo cp -R --no-preserve=ownership "$CANDIDATE" "$REVIEW"
sudo chown -R root:root "$REVIEW"
sudo find "$REVIEW" -type d -exec chmod 0755 {} +
sudo find "$REVIEW" -type f -exec chmod 0444 {} +
sudo find "$REVIEW/runtime" -type f -exec chmod 0555 {} +
sudo chmod 0555 "$REVIEW/build-tools/uv"
# Use the system interpreter only to check trusted bytes before using the approved runtime.
sudo /usr/bin/python3 -I -B - "$REVIEW" <<'PY'
import runpy,sys
from pathlib import Path
r=Path(sys.argv[1])
for p in (r,*r.parents):
 s=p.stat();assert s.st_uid==0 and not s.st_mode & 0o022,p
# Check installer hash before loading its verification functions.
import hashlib,json
m=r/'manifest.json'
assert hashlib.sha256(m.read_bytes()).hexdigest()=='abd32ba809820aa061e9f679234df8beabc27178121cf30b2fa472cc8e052275'
p=r/'install_host_review.py'
assert not p.is_symlink() and p.stat().st_uid==0 and not p.stat().st_mode & 0o022
assert hashlib.sha256(p.read_bytes()).hexdigest()==json.loads(m.read_text())['files']['install_host_review.py']
x=runpy.run_path(str(p))
x['verify_review'](r,'abd32ba809820aa061e9f679234df8beabc27178121cf30b2fa472cc8e052275')
x['verify_python']('/opt/jarvis-codex/runtime/bin/python3.13')
print('Root review and approved Python runtime verified without modification')
PY
)
```

Python 3.13.16 and its CPython source checksum remain the approved [existing operator pin](phase5b-operator-unblock-guide.md). The verifier checks runtime-pin.json, executable digest, the whole root-owned non-writable tree and links. It does not change that runtime. The uv binary is included with its recorded 0.12.23 digest; no curl-to-shell installer is used.

## 3. Provision only the new non-login identity

```bash
(
set -euo pipefail
ACCOUNT=jarvis-codex-engineering
STATE=/var/lib/rras-engineering
if getent passwd "$ACCOUNT" || getent group "$ACCOUNT"; then exit 1; fi
sudo test ! -e "$STATE"
sudo test ! -L "$STATE"
sudo useradd --system --user-group --home-dir "$STATE" --no-create-home --shell /usr/sbin/nologin "$ACCOUNT"
id "$ACCOUNT"
getent passwd "$ACCOUNT"
# Review this output: stop if any sudo commands are granted; do not expand permissions.
sudo -l -U "$ACCOUNT" || true
)
```

The account must have only its dedicated primary group, a unique UID distinct from operator/supervisor/nobody, and no sudo rules, Docker/LXD/NAS/admin access. Do not run the account block again after creation. The installer verifies identity and groups, but the administrator must review user-specific sudo grants separately.

## 4. Build the new immutable release and private state

```bash
(
set -euo pipefail
REVIEW=/opt/rras-engineering-review-10
PYTHON=/opt/jarvis-codex/runtime/bin/python3.13
sudo "$PYTHON" -I -B "$REVIEW/install_host_review.py" \
 --review "$REVIEW" \
 --manifest-sha256 abd32ba809820aa061e9f679234df8beabc27178121cf30b2fa472cc8e052275 \
 --python "$PYTHON" --release-id native-10
sudo cat /opt/rras-engineering/releases/native-10/installation-result.json
)
```

The dependency build may fetch public pinned artifacts and runs only installation/build code. Cleared environment, isolated cache, frozen lock, no extras, no Python download, no credentials or inference. It creates root-owned `/opt/rras-engineering/releases/native-10` and worker-owned 0700 `/var/lib/rras-engineering`. Configs contain API **environment-variable names**, not keys. Named profile and separate Codex home are created explicitly. Default concurrency/spawn caps are one; gateway dispatch remains disabled for manual-first use. Root directory modes are explicitly verified/set for newly created paths so umask 077 cannot silently make release ancestors untraversable.

Hermes 0.20.4 intentionally rejects wheel/non-editable builds: the disposable `--no-editable` validation failed before installation. Its [pinned setup.py](https://github.com/NousResearch/hermes-agent/blob/76952ba54f5dd83f4f5bd0246059171b4b9d1c4a/setup.py) explicitly permits editable builds. Here that mechanism points only at the fixed, root-owned release source, not a worker-writable development checkout. No Nix guard bypass or patch is used. Current upstream install docs describe a newer toolchain; this procedure remains pinned to the verified 0.20.4 source.

No service, current symlink, board task, admitted repository or timer is created. New state is not production acceptance. Do not copy a temporary venv into this release.

## 5. Actual dedicated-UID sandbox acceptance

```bash
(
set -euo pipefail
RELEASE=/opt/rras-engineering/releases/native-10
ACCOUNT=jarvis-codex-engineering
STATE=/var/lib/rras-engineering
RUN_ID=$(python3 -I -B -c 'import uuid;print(uuid.uuid4().hex)')
UNIT="rras-host-boundary-$RUN_ID"
WORK="$STATE/acceptance-$RUN_ID"
ROOT_FIXTURE="/opt/rras-engineering/acceptance-root-$RUN_ID"
WORKER_UID=$(id -u "$ACCOUNT")
WORKER_GID=$(id -g "$ACCOUNT")
sudo test ! -e "$WORK"
sudo test ! -L "$WORK"
sudo test ! -e "$ROOT_FIXTURE"
test "$(systemctl show "$UNIT.service" -p LoadState --value)" = not-found
printf 'SAVE RUN_ID=%s UNIT=%s WORK=%s ROOT_FIXTURE=%s\n' "$RUN_ID" "$UNIT" "$WORK" "$ROOT_FIXTURE"
sudo install -d -o "$WORKER_UID" -g "$WORKER_GID" -m 0700 "$WORK"
sudo install -d -o root -g root -m 0711 "$ROOT_FIXTURE"
printf 'Harmless cross-UID acceptance fixture; no secret\n' | sudo tee "$ROOT_FIXTURE/sentinel" >/dev/null
sudo chmod 0600 "$ROOT_FIXTURE/sentinel"
sudo systemd-run --unit "$UNIT" --service-type=exec --wait --pipe --collect \
 -p "User=$ACCOUNT" -p "Group=$ACCOUNT" -p "WorkingDirectory=$WORK" \
 -p UMask=0077 -p NoNewPrivileges=yes -p 'CapabilityBoundingSet=' \
 -p KillMode=control-group -p RuntimeMaxSec=60 -p TimeoutStopSec=10 \
 -p MemoryMax=1G -p TasksMax=128 -p CPUQuota=100% \
 /usr/bin/env -i PATH=/usr/bin:/bin HOME="$WORK" LANG=C.UTF-8 \
 "$RELEASE/venv/bin/python" -I -B "$RELEASE/probe_host_worker.py" \
 --uid "$WORKER_UID" --gid "$WORKER_GID" --protected-fixture "$ROOT_FIXTURE/sentinel" \
 --binary "$RELEASE/runtime/bin/codex" --config-template "$RELEASE/codex/config.toml" \
 --evidence "$WORK/codex-evidence.json" 2>&1 | sudo tee "$WORK/acceptance-output.log"
sudo /usr/bin/python3 -I -B - "$WORK" <<'PY'
import json,sys
from pathlib import Path
w=Path(sys.argv[1]);identity=json.loads((w/'identity-evidence.json').read_text());coding=json.loads((w/'codex-evidence.json').read_text())
assert identity['success'] and coding['success']
assert all(c['passed'] for c in coding['cases'])
assert {c['name'] for c in coding['cases']}=={'initialize','workspace_write','board_write','sibling_write_denied','network_denied'}
print('Actual dedicated-UID identity and five native sandbox checks passed')
PY
)
```

This is a transient acceptance service, not production automation. It requests no model turn. Network denial is tested **inside Codex**, with a positive host loopback control; no global service network denial masks a broken sandbox. Fixture/root sentinel, machine-readable failure output and receipt paths are retained. The pipefail setting preserves a failed service status while tee retains its output; do not treat the presence of a log as acceptance. Do not clear native or legacy fences or delete records after a failure.

## 6. Stop and retain the checkpoint

After acceptance, return its exact saved run ID and evidence. Do not add an API key or run a paid task yet. Next source/session gate: effective native callback/tool inventory and fail-closed approval handling, then reviewed repo admission/manual one-pass task invocation and separately authorized canary. Native persistent dispatcher/cgroup worker-stop acceptance belongs to the later unattended Jarvis milestone.

There is deliberately no activation command or installed-unit rollback: this procedure installs none. Keep the reconciliation timer disabled. Do not infer authenticated cancellation, adversarial per-task isolation, or real-session success from these model-free checks.

## Partial install recovery and rollback

- **Root review copy fails:** do not overwrite it. Inspect/retain `/opt/rras-engineering-review-10`; choose a fresh review destination after comparing the manifest. No account/state/service has changed at that step.
- **Account creation succeeded, later step failed:** retain the account and its allocated IDs. Do not repeat useradd, add groups, or delete/recreate it. Resume only after verifying the same account satisfies the installer checks.
- **Dependency build failed before state creation:** inspect `installation-result.json` and `dependency-build.log`. Confirm `phase=failed`, `state_created=false`, and `/var/lib/rras-engineering` absent. Preserve native-10 and rerun the same root review with `--release-id native-10-retry1`; the state still must be absent. No release is overwritten.
- **State exists after partial failure:** do not rerun/adopt it or recursively change ownership. Preserve it. Confirm there are no processes under the dedicated UID, review the exact result and contents without printing secrets, then obtain a concrete recovery plan. A power loss between state mkdir and result update is intentionally ambiguous; absence-only behavior prevents automatic adoption.
- **Acceptance failure:** retain WORK, ROOT_FIXTURE and the exact transient unit status. Stop only the confirmed created unit if it is still active; no wildcard cleanup. A planned name after a failed/lost creation response does not establish ownership. `RuntimeMaxSec=60` bounds normal fixture lifetime; verify termination before any cleanup. Do not signal existing Hermes processes.
- **Rollback without deleting evidence:** stop any *confirmed* transient acceptance unit, verify the dedicated UID has no live processes, and leave the new release/account/state inactive and retained. Existing application selection is unchanged because no current symlink/unit was installed. No production migration or credential exists to undo. Any later archival/removal is a separately reviewed exact-path operation, not part of this procedure.

Self-contained read-only failure inspection (prompts for the saved exact unit; no placeholders to paste):

```bash
(
set -euo pipefail
printf 'Paste the saved exact RRAS host acceptance unit (rras-host-boundary-32hex): '
IFS= read -r UNIT
[[ "$UNIT" =~ ^rras-host-boundary-[a-f0-9]{32}$ ]] || exit 1
sudo systemctl show "$UNIT.service" -p LoadState -p ActiveState -p SubState -p Result -p ControlGroup -p User -p ExecStart
# This block does not stop/adopt any unit or remove evidence.
)
```
