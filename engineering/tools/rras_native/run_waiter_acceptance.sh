#!/usr/bin/env bash
(
set -euo pipefail
CANDIDATE=/tmp/rras-waiter-review-20261012-01
REVIEW=/opt/rras-waiter-review-20261012-01
PYTHON=/opt/jarvis-codex/runtime/bin/python3.13
ACCOUNT=jarvis-codex-engineering
PIN=e33830fb7b626d884b2aeae96d97f6e2a46fd16490b59a6d7d3d8660c40b7202
RUN_ID=$(python3 -I -B -c 'import uuid;print(uuid.uuid4().hex)')
UNIT=rras-waiter-$RUN_ID
WORK=/var/lib/rras-engineering/waiter-$RUN_ID
sudo -v
test "$(hostname -s)" = server01
test "$(id -u "$ACCOUNT")" = 996
test "$(id -g "$ACCOUNT")" = 996
test "$(id -G "$ACCOUNT")" = 996
test "$(systemctl is-enabled jarvis-codex-reconcile.timer || true)" = disabled
test "$(systemctl is-active jarvis-codex-reconcile.service || true)" = inactive
python3 -I -B - "$CANDIDATE" "$PIN" <<'PY'
import hashlib,json,sys
from pathlib import Path
r=Path(sys.argv[1]);m=r/'manifest.json'
assert hashlib.sha256(m.read_bytes()).hexdigest()==sys.argv[2]
f=json.loads(m.read_text())
assert {p.name for p in r.iterdir()}==set(f)|{'manifest.json','operator-acceptance.sh'}
assert (r/'operator-acceptance.sh').is_file() and not (r/'operator-acceptance.sh').is_symlink()
for n,h in f.items():
 p=r/n;assert p.is_file() and not p.is_symlink()
 assert hashlib.sha256(p.read_bytes()).hexdigest()==h,n
PY
sudo test ! -e "$REVIEW"
sudo test ! -L "$REVIEW"
sudo test ! -e "$WORK"
sudo test ! -L "$WORK"
test "$(systemctl show "$UNIT.service" -p LoadState --value)" = not-found
printf 'SAVE RUN_ID=%s UNIT=%s WORK=%s\n' "$RUN_ID" "$UNIT" "$WORK"
sudo install -d -o root -g root -m 0755 "$REVIEW"
for NAME in wait_worker.py probe_wait_worker.py manifest.json; do
 sudo install -o root -g root -m 0444 "$CANDIDATE/$NAME" "$REVIEW/$NAME"
done
sudo /usr/bin/python3 -I -B - "$REVIEW" "$PIN" <<'PY'
import hashlib,json,sys
from pathlib import Path
r=Path(sys.argv[1]);m=r/'manifest.json'
assert hashlib.sha256(m.read_bytes()).hexdigest()==sys.argv[2]
for p in (r,*r.parents):
 s=p.stat();assert s.st_uid==0 and not s.st_mode & 0o022,p
for n,h in json.loads(m.read_text()).items():
 p=r/n;s=p.stat();assert not p.is_symlink() and s.st_uid==0 and not s.st_mode & 0o022
 assert hashlib.sha256(p.read_bytes()).hexdigest()==h,n
PY
sudo install -d -o 996 -g 996 -m 0700 "$WORK"
sudo systemd-run --unit "$UNIT" --service-type=exec --wait --pipe --collect \
 -p User="$ACCOUNT" -p Group="$ACCOUNT" -p WorkingDirectory="$WORK" \
 -p UMask=0077 -p NoNewPrivileges=yes -p 'CapabilityBoundingSet=' \
 -p PrivateNetwork=yes -p KillMode=control-group -p RuntimeMaxSec=30 -p TimeoutStopSec=5 \
 -p MemoryMax=512M -p TasksMax=32 -p CPUQuota=100% \
 /usr/bin/env -i PATH=/usr/bin:/bin HOME="$WORK" LANG=C.UTF-8 \
 "$PYTHON" -I -B "$REVIEW/probe_wait_worker.py" --work "$WORK" --dedicated-cgroup \
 2>&1 | sudo tee "$WORK/output.log"
sudo /usr/bin/python3 -I -B - "$WORK/evidence.json" <<'PY'
import json,sys
e=json.load(open(sys.argv[1]))
assert e['uid']==996 and e['success'] and e['dedicated_cgroup_tested']
assert e['api_calls']==0 and len(e['cases'])==5 and all(c['passed'] for c in e['cases'])
print('Dedicated-cgroup model-free waiter acceptance passed')
print(json.dumps(e,indent=2))
PY
printf 'RETAIN RUN_ID=%s WORK=%s\n' "$RUN_ID" "$WORK"
)
