#!/usr/bin/env bash
(
set -euo pipefail
CANDIDATE=/tmp/rras-integrated-review-20261012-01
REVIEW=/opt/rras-integrated-review-20261012-01
PYTHON=/opt/rras-engineering/releases/native-10/venv/bin/python
ACCOUNT=jarvis-codex-engineering
PIN=b17ef32b5b7d3bcbd38f5fe4b58cbf3a53227306e0b067182908de4a971393c9
RUN_ID=$(python3 -I -B -c 'import uuid;print(uuid.uuid4().hex)')
UNIT=rras-integrated-$RUN_ID
WORK=/var/lib/rras-engineering/integrated-$RUN_ID
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
for NAME in wait_worker.py probe_integrated_runner.py activity.py profile.json manifest.json; do
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
for CASE in success crash timeout; do
 CASE_WORK="$WORK/$CASE"
 CASE_UNIT="$UNIT-$CASE"
 test "$(systemctl show "$CASE_UNIT.service" -p LoadState --value)" = not-found
 sudo install -d -o 996 -g 996 -m 0700 "$CASE_WORK"
 sudo systemd-run --unit "$CASE_UNIT" --service-type=exec --wait --pipe --collect \
  -p User="$ACCOUNT" -p Group="$ACCOUNT" -p WorkingDirectory="$CASE_WORK" \
  -p UMask=0077 -p NoNewPrivileges=yes -p 'CapabilityBoundingSet=' \
  -p PrivateNetwork=yes -p KillMode=control-group -p RuntimeMaxSec=45 -p TimeoutStopSec=5 \
  -p MemoryMax=1G -p TasksMax=128 -p CPUQuota=100% \
  /usr/bin/env -i PATH=/usr/bin:/bin HOME="$CASE_WORK" LANG=C.UTF-8 PYTHONDONTWRITEBYTECODE=1 \
  "$PYTHON" -I -B "$REVIEW/probe_integrated_runner.py" \
  --source /opt/rras-engineering/releases/native-10/hermes --python "$PYTHON" \
  --profile "$REVIEW/profile.json" --work "$CASE_WORK" --case "$CASE" --dedicated-cgroup \
  2>&1 | sudo tee "$CASE_WORK/output.log"
done
sudo /usr/bin/python3 -I -B - "$WORK" <<'PY'
import json,sys
from pathlib import Path
r=Path(sys.argv[1]);results={c:json.loads((r/c/'evidence.json').read_text()) for c in ('success','crash','timeout')}
for c,e in results.items():
 assert e['uid']==996 and e['success'] and e['dedicated_cgroup'] and e['api_calls']==0
 assert e['wait']['outcome']=={'success':'completed','crash':'failed','timeout':'timeout'}[c]
 assert not e['lifecycle_mutated_by_runner']
assert results['success']['validation_exit']==0 and results['success']['export']
assert results['crash']['validation_exit']!=0 and results['crash']['export']
assert not results['timeout']['wait']['worker_stop_verified'] and 'export' not in results['timeout']
cleanup=json.loads((r/'timeout/fixture-cleanup.json').read_text())
assert cleanup['owned_fake_child_stopped'] and not cleanup['native_lifecycle_mutated']
print('Dedicated native integration: success, crash and timeout acceptance passed')
print(json.dumps(results,indent=2))
PY
printf 'RETAIN RUN_ID=%s WORK=%s UNIT_PREFIX=%s\n' "$RUN_ID" "$WORK" "$UNIT"
)
