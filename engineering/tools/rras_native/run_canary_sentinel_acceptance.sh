#!/usr/bin/env bash
# Model-free fixture only. Never supply a real credential to this script.
(
set -euo pipefail
CANDIDATE=/tmp/rras-canary-review-20261012-02
REVIEW=/opt/rras-canary-review-20261012-02
RELEASE=/opt/rras-engineering/releases/native-10
ACCOUNT=jarvis-codex-engineering
MANIFEST=7edf81ed5221221444f25dbb4a5692f4a62ba1daf94440459692f4a1400a5a73
RUN_ID=$(python3 -I -B -c 'import uuid;print(uuid.uuid4().hex)')
WORK=/var/lib/rras-engineering/canary-sentinel-$RUN_ID
SOURCE_ROOT=/opt/rras-canary-sentinel-source-$RUN_ID
UNIT=rras-canary-sentinel-$RUN_ID
sudo -v
test "$(hostname -s)" = server01
test "$(id -u "$ACCOUNT")" = 996
test "$(id -g "$ACCOUNT")" = 996
test "$(id -G "$ACCOUNT")" = 996
test "$(systemctl is-enabled jarvis-codex-reconcile.timer || true)" = disabled
test "$(systemctl is-active jarvis-codex-reconcile.service || true)" = inactive
python3 -I -B - "$CANDIDATE" "$MANIFEST" <<'PY'
import hashlib,json,sys
from pathlib import Path
r=Path(sys.argv[1]);m=r/'manifest.json'
assert hashlib.sha256(m.read_bytes()).hexdigest()==sys.argv[2]
f=json.loads(m.read_text())
assert set(f)=={'probe_cli_credentials.py','probe_native_credential_handoff.py','probe_integrated_runner.py','manual_paid_canary.py','wait_worker.py','activity.py','profile.json','codex-config.toml'}
assert {p.name for p in r.iterdir()}==set(f)|{'manifest.json','operator-acceptance.sh'}
assert (r/'operator-acceptance.sh').is_file() and not (r/'operator-acceptance.sh').is_symlink()
for n,h in f.items():
 p=r/n
 assert p.is_file() and not p.is_symlink()
 assert hashlib.sha256(p.read_bytes()).hexdigest()==h,n
PY
for DESTINATION in "$REVIEW" "$WORK" "$SOURCE_ROOT"; do
 sudo test ! -e "$DESTINATION"
 sudo test ! -L "$DESTINATION"
done
test "$(systemctl show "$UNIT.service" -p LoadState --value)" = not-found
printf 'SAVE RUN_ID=%s UNIT=%s WORK=%s SOURCE_ROOT=%s\n' "$RUN_ID" "$UNIT" "$WORK" "$SOURCE_ROOT"
sudo install -d -o root -g root -m 0755 "$REVIEW"
for NAME in probe_cli_credentials.py probe_native_credential_handoff.py probe_integrated_runner.py manual_paid_canary.py wait_worker.py activity.py profile.json codex-config.toml manifest.json; do
 sudo install -o root -g root -m 0444 "$CANDIDATE/$NAME" "$REVIEW/$NAME"
done
sudo /usr/bin/python3 -I -B - "$REVIEW" "$MANIFEST" "$RELEASE" <<'PY'
import hashlib,json,sys
from pathlib import Path
r=Path(sys.argv[1]);release=Path(sys.argv[3]);m=r/'manifest.json'
assert hashlib.sha256(m.read_bytes()).hexdigest()==sys.argv[2]
for p in (r,*r.parents,release,*release.parents):
 s=p.stat();assert s.st_uid==0 and not s.st_mode & 0o022,p
for n,h in json.loads(m.read_text()).items():
 p=r/n;s=p.stat()
 assert not p.is_symlink() and s.st_uid==0 and not s.st_mode & 0o022
 assert hashlib.sha256(p.read_bytes()).hexdigest()==h,n
receipt=json.loads((release/'installation-result.json').read_text())
assert receipt['phase']=='installed-disabled' and receipt['uid']==996 and receipt['gid']==996
PY
sudo install -d -o root -g root -m 0711 "$SOURCE_ROOT"
printf 'RRAS-NONSECRET-OFFLINE-FIXTURE\n' | sudo tee "$SOURCE_ROOT/fixture" >/dev/null
sudo chmod 0600 "$SOURCE_ROOT/fixture"
sudo install -d -o 996 -g 996 -m 0700 "$WORK"
sudo systemd-run --unit "$UNIT" --service-type=exec --wait --pipe --collect \
 -p User="$ACCOUNT" -p Group="$ACCOUNT" -p WorkingDirectory="$WORK" \
 -p UMask=0077 -p NoNewPrivileges=yes -p 'CapabilityBoundingSet=' \
 -p PrivateNetwork=yes -p KillMode=control-group \
 -p RuntimeMaxSec=90 -p TimeoutStopSec=10 \
 -p MemoryMax=1G -p TasksMax=128 -p CPUQuota=100% \
 -p "LoadCredential=rras-fixture:$SOURCE_ROOT/fixture" \
 /usr/bin/env -i PATH=/usr/bin:/bin HOME="$WORK" LANG=C.UTF-8 \
 PYTHONDONTWRITEBYTECODE=1 'CREDENTIALS_DIRECTORY=${CREDENTIALS_DIRECTORY}' \
 "$RELEASE/venv/bin/python" -I -B "$REVIEW/probe_native_credential_handoff.py" \
 --source "$RELEASE/hermes" --python "$RELEASE/venv/bin/python" --profile "$REVIEW/profile.json" \
 --codex-config "$REVIEW/codex-config.toml" --work "$WORK" \
 --credential '${CREDENTIALS_DIRECTORY}/rras-fixture' --dedicated-cgroup \
 2>&1 | sudo tee "$WORK/output.log"
sudo /usr/bin/python3 -I -B - "$WORK" <<'PY'
import json,sys
from pathlib import Path
w=Path(sys.argv[1]);e=json.loads((w/'evidence.json').read_text());d=json.loads((w/'delivery.json').read_text())
assert e['uid']==996 and e['success'] and e['dedicated_cgroup'] and e['api_calls']==0
assert e['wait']['worker_stop_verified'] and e['validation_exit']==0 and e['export']
assert all(e['sentinel_handoff'].values())
assert d['systemd_delivery'] and d['production_loader_validated']
print('Systemd sentinel + native spawn + App Server environment handoff passed')
print(json.dumps(e,indent=2));print(json.dumps(d))
PY
printf 'RETAIN RUN_ID=%s WORK=%s SOURCE_ROOT=%s\n' "$RUN_ID" "$WORK" "$SOURCE_ROOT"
)
