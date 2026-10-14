#!/usr/bin/env bash
# Exactly one operator-authorized paid canary. Never automatically rerun.
(
set -euo pipefail
# Set only after explicit authorization of a new paid attempt.
test "${RRAS_AUTHORIZE_ONE_PAID_TASK:-}" = reviewed-canary-20261012-05
REVIEW=/opt/rras-canary-review-20261012-05
RELEASE=/opt/rras-engineering/releases/native-10
KEY_SOURCE=/etc/rras-canary-credentials-20261012-01/openai_api_key
ACCOUNT=jarvis-codex-engineering
RUN_ID=$(python3 -I -B -c 'import uuid;print(uuid.uuid4().hex)')
UNIT=rras-paid-canary-$RUN_ID
WORK=/var/lib/rras-engineering/paid-canary-$RUN_ID
sudo -v
test "$(hostname -s)" = server01
test "$(id -u "$ACCOUNT")" = 996
test "$(id -G "$ACCOUNT")" = 996
test "$(systemctl is-enabled jarvis-codex-reconcile.timer || true)" = disabled
test "$(systemctl is-active jarvis-codex-reconcile.service || true)" = inactive
OLD_UNIT=rras-paid-canary-56c1a14547d441c0931336a437318fd3
OLD_WORK=/var/lib/rras-engineering/paid-canary-56c1a14547d441c0931336a437318fd3
CANDIDATE=/tmp/rras-canary-review-20261012-05
OLD_STATE=$(systemctl show "$OLD_UNIT.service" -p ActiveState --value)
[[ "$OLD_STATE" = inactive || "$OLD_STATE" = failed ]] || exit 1
if pgrep -u "$ACCOUNT" >/dev/null; then echo 'STOP: dedicated UID has live processes'; exit 1; fi
sudo /usr/bin/python3 -I -B - "$OLD_WORK" "$CANDIDATE" <<'PY'
import hashlib,json,sys
from pathlib import Path
old=Path(sys.argv[1]);r=Path(sys.argv[2])
assert old.is_dir() and not old.is_symlink()
evidence=old/'evidence.json'
assert evidence.is_file() and not evidence.is_symlink()
e=json.loads(evidence.read_text())
assert e['scope']=='native-manual-paid-canary' and e['success'] is False
assert e['native_task']=='t_2563a5dd' and e['native_run']==1
assert e['wait']['outcome']=='failed' and e['lifecycle_mutated_by_runner'] is False
assert e['wait']['exit_code']==0 and e['wait']['worker_stop_verified'] is True
assert e['validation_exit']==0 and e['export']['export_id']=='c1bd28c77905f3cbbae3bcb360df7f430b0f8bfc3c6109fd850687136a8d4dff'
# Preserve the old native task and failed-completion receipt; current process absence is checked above.
assert hashlib.sha256((r/'manifest.json').read_bytes()).hexdigest()=='f272364f9dec3c19f635f1b702a083e6f1be33512efb81ea6636c13d50a763d6'
f=json.loads((r/'manifest.json').read_text())
assert {p.name for p in r.iterdir()}==set(f)|{'manifest.json'}
for n,h in f.items():
 p=r/n;assert not p.is_symlink() and p.is_file()
 assert hashlib.sha256(p.read_bytes()).hexdigest()==h,n
print('Retained failed-completion receipt and fresh candidate verified without reading credentials')
PY
sudo test ! -e "$REVIEW"
sudo test ! -L "$REVIEW"
sudo install -d -o root -g root -m 0755 "$REVIEW"
for NAME in manual_paid_canary.py probe_integrated_runner.py probe_native_credential_handoff.py probe_cli_credentials.py wait_worker.py activity.py native_task_cli.py profile.json codex-config.toml manifest.json; do
 sudo install -o root -g root -m 0444 "$CANDIDATE/$NAME" "$REVIEW/$NAME"
done
sudo /usr/bin/python3 -I -B - "$REVIEW" "$KEY_SOURCE" <<'PY'
import hashlib,json,stat,sys
from pathlib import Path
r=Path(sys.argv[1]);m=r/'manifest.json'
assert hashlib.sha256(m.read_bytes()).hexdigest()=='f272364f9dec3c19f635f1b702a083e6f1be33512efb81ea6636c13d50a763d6'
for p in (r,*r.parents):
 s=p.stat();assert s.st_uid==0 and not s.st_mode & 0o022,p
for n,h in json.loads(m.read_text()).items():
 p=r/n;s=p.stat()
 assert not p.is_symlink() and s.st_uid==0 and not s.st_mode & 0o022,n
 assert hashlib.sha256(p.read_bytes()).hexdigest()==h,n
runtime=Path('/opt/rras-engineering/releases/native-10/venv/bin/python')
for p in (runtime,*runtime.parents,runtime.resolve(strict=True),*runtime.resolve(strict=True).parents):
 s=p.stat();assert s.st_uid==0 and (p.is_symlink() or not s.st_mode & 0o022),p
key=Path(sys.argv[2])
# Metadata only: do not read or print the key.
assert not key.is_symlink() and key.resolve()==key
s=key.stat()
assert stat.S_ISREG(s.st_mode) and s.st_uid==0 and not s.st_mode & 0o077, 'Stop: key source must be root-owned and private; preserve it'
assert 1<=s.st_size<=16384, 'Stop: unexpected credential file size'
for p in key.parents:
 s=p.stat();assert s.st_uid==0 and not s.st_mode & 0o022, 'Stop: untrusted credential ancestor; do not change ownership'
print('Reviewed code and non-secret key-source metadata verified')
PY
sudo test ! -e "$WORK"
sudo test ! -L "$WORK"
test "$(systemctl show "$UNIT.service" -p LoadState --value)" = not-found
printf 'SAVE PAID RUN_ID=%s UNIT=%s WORK=%s\n' "$RUN_ID" "$UNIT" "$WORK"
sudo install -d -o 996 -g 996 -m 0700 "$WORK"
# Provider control-plane network is allowed; Codex coding sandbox remains network-off.
sudo systemd-run --unit "$UNIT" --service-type=exec --wait --pipe --collect \
 -p User="$ACCOUNT" -p Group="$ACCOUNT" -p WorkingDirectory="$WORK" \
 -p UMask=0077 -p NoNewPrivileges=yes -p 'CapabilityBoundingSet=' \
 -p KillMode=control-group -p RuntimeMaxSec=360 -p TimeoutStopSec=10 \
 -p MemoryMax=1G -p TasksMax=128 -p CPUQuota=100% \
 -p "LoadCredential=rras-api:$KEY_SOURCE" \
 /usr/bin/env -i PATH=/usr/bin:/bin HOME="$WORK" LANG=C.UTF-8 PYTHONDONTWRITEBYTECODE=1 \
 'CREDENTIALS_DIRECTORY=${CREDENTIALS_DIRECTORY}' \
 "$RELEASE/venv/bin/python" -I -B "$REVIEW/manual_paid_canary.py" \
 --source "$RELEASE/hermes" --python "$RELEASE/venv/bin/python" \
 --profile "$REVIEW/profile.json" --codex-config "$REVIEW/codex-config.toml" \
 --work "$WORK" --credential '${CREDENTIALS_DIRECTORY}/rras-api' --authorize-one-paid-task \
 2>&1 | sudo tee "$WORK/operator-output.log"
sudo /usr/bin/python3 -I -B - "$WORK/evidence.json" <<'PY'
import json,sys
e=json.load(open(sys.argv[1]))
assert e['scope']=='native-manual-paid-canary' and e['uid']==996 and e['success']
assert e['wait']['success'] and e['wait']['worker_stop_verified']
assert e['validation_exit']==0 and e['export']
print('Paid canary result recorded; human review remains required')
print(json.dumps(e,indent=2))
PY
printf 'RETAIN PAID RUN_ID=%s UNIT=%s WORK=%s\n' "$RUN_ID" "$UNIT" "$WORK"
)
