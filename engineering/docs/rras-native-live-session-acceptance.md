# Live native session acceptance

2026-10-07. Development fixture passed eight live checks using the pinned actual Hermes session/client/environment helper and installed Codex 0.159.0. No helper stubs, credentials, model turns or MCP callbacks. App-server process termination verified. [Development evidence](rras-native-live-session-development-evidence.json) is UID 1000, **not dedicated-UID acceptance**. Focused suite: 33 passed. Existing installed release, state records, services and timer untouched.

The probe checks actual child /proc environment for isolated CODEX_HOME, actual child cwd, thread startup, effective config/read sandbox/approval/network policy, and absence of configured MCP/apps. It does not enumerate all built-in tool schemas, test a real turn's callbacks, certify descendant cgroup termination, or establish authentication/model entitlement. No configured MCP/apps is narrower than exhaustive tool discovery. Review these limits alongside [session policy findings](rras-native-session-policy-review.md). The first coding lane uses native Codex tools; do not enable Hermes MCP migration.

Dedicated run is pending: noninteractive sudo required a password. Execute the following complete block on server01. It publishes only a new standalone reviewed probe; it does not update native-10. Stop on failure and retain all evidence. Never overwrite either review destination or fixture. The transient unit has a 60-second bound and no model task.

```bash
(
set -euo pipefail
CANDIDATE=/tmp/rras-live-session-review-20261007-01
REVIEW=/opt/rras-live-session-review-20261007-01
RELEASE=/opt/rras-engineering/releases/native-10
ACCOUNT=jarvis-codex-engineering
RUN_ID=$(python3 -I -B -c 'import uuid; print(uuid.uuid4().hex)')
WORK=/var/lib/rras-engineering/live-session-$RUN_ID
UNIT=rras-live-session-$RUN_ID
EXPECTED=5b0493d0b5904736a6a141e45633e98e8bb4b0034b0e87a978220715286140d8
sudo -v
test "$(hostname -s)" = server01
test "$(id -u "$ACCOUNT")" = 996
test "$(id -g "$ACCOUNT")" = 996
test "$(id -G "$ACCOUNT")" = 996
test "$(systemctl is-enabled jarvis-codex-reconcile.timer || true)" = disabled
test "$(systemctl is-active jarvis-codex-reconcile.service || true)" = inactive
test "$(sha256sum "$CANDIDATE/probe_live_session.py" | cut -d ' ' -f1)" = "$EXPECTED"
sudo test ! -e "$REVIEW"
sudo test ! -L "$REVIEW"
sudo install -d -o root -g root -m 0755 "$REVIEW"
sudo install -o root -g root -m 0444 "$CANDIDATE/probe_live_session.py" "$REVIEW/probe_live_session.py"
test "$(sha256sum "$REVIEW/probe_live_session.py" | cut -d ' ' -f1)" = "$EXPECTED"
sudo test ! -e "$WORK"
sudo test ! -L "$WORK"
test "$(systemctl show "$UNIT.service" -p LoadState --value)" = not-found
printf 'SAVE RUN_ID=%s UNIT=%s WORK=%s\n' "$RUN_ID" "$UNIT" "$WORK"
sudo install -d -o 996 -g 996 -m 0700 "$WORK"
sudo systemd-run --unit "$UNIT" --service-type=exec --wait --pipe --collect \
 -p User="$ACCOUNT" -p Group="$ACCOUNT" -p WorkingDirectory="$WORK" \
 -p UMask=0077 -p NoNewPrivileges=yes -p 'CapabilityBoundingSet=' \
 -p KillMode=control-group -p RuntimeMaxSec=60 -p TimeoutStopSec=10 \
 -p MemoryMax=1G -p TasksMax=128 -p CPUQuota=100% \
 /usr/bin/env -i PATH=/usr/bin:/bin HOME="$WORK" LANG=C.UTF-8 PYTHONDONTWRITEBYTECODE=1 \
 "$RELEASE/venv/bin/python" -I -B "$REVIEW/probe_live_session.py" \
 --source "$RELEASE/hermes" --binary "$RELEASE/runtime/bin/codex" \
 --config "$RELEASE/codex/config.toml" --work "$WORK" --uid 996 \
 2>&1 | sudo tee "$WORK/output.log"
sudo /usr/bin/python3 -I -B - "$WORK/evidence.json" <<'PY'
import json,sys
e=json.load(open(sys.argv[1]))
assert e['uid']==996 and e['success'] and e['app_server_stopped']
assert e['api_calls']==0 and e['inference_requests']==0
assert len(e['cases'])==8 and all(c['passed'] for c in e['cases'])
print('Dedicated-UID live native session acceptance passed')
PY
sudo cat "$WORK/evidence.json"
test "$(systemctl is-enabled jarvis-codex-reconcile.timer || true)" = disabled
printf 'RETAIN RUN_ID=%s WORK=%s\n' "$RUN_ID" "$WORK"
)
```

After success retain review/fixtures/evidence. No deletion or permanent service activation is needed. On failure preserve the exact unit and WORK; inspect only the saved exact unit with systemctl show. Stop only a confirmed-created still-running unit, never wildcard names; verify termination before any archival. If the review was published and a later step failed, do not republish or rerun the entire block. Return the exact failure for a resume procedure. Session startup errors retain type only to avoid leaking provider/auth diagnostics.

Next after this acceptance: disposable repository admission/native project and worktree binding, reviewed manual one-pass invocation and export. A separately authorized paid canary follows credential provisioning; unattended dispatcher lifecycle remains later work.
