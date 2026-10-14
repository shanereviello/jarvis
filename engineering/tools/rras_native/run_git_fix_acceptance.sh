#!/usr/bin/env bash
(
set -euo pipefail
CANDIDATE=/tmp/rras-git-fix-review-20261012-03
REVIEW=/opt/rras-git-fix-review-20261012-03
PYTHON=/opt/rras-engineering/releases/native-10/venv/bin/python
ACCOUNT=jarvis-codex-engineering
PIN=3da2bd252cb66c37ae704d5d9bdbd1fdb5645f4ad6af9f3cfa6b8e2b2b9fc745
RUN_ID=$(python3 -I -B -c 'import uuid;print(uuid.uuid4().hex)')
UNIT=rras-git-fix-$RUN_ID
WORK=/var/lib/rras-engineering/git-fix-$RUN_ID
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
for NAME in wait_worker.py probe_git_metadata.py probe_integrated_runner.py activity.py manifest.json; do
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
 -p PrivateNetwork=yes -p KillMode=control-group -p RuntimeMaxSec=60 -p TimeoutStopSec=5 \
 -p MemoryMax=512M -p TasksMax=128 -p CPUQuota=100% \
 /usr/bin/env -i PATH=/usr/bin:/bin HOME="$WORK" LANG=C.UTF-8 \
 "$PYTHON" -I -B "$REVIEW/probe_git_metadata.py" --source /opt/rras-engineering/releases/native-10/hermes --python "$PYTHON" --parent "$WORK" \
 2>&1 | sudo tee "$WORK/output.log"
sudo /usr/bin/python3 -I -B - "$WORK" <<'PY'
import json,sys
from pathlib import Path
files=list(Path(sys.argv[1]).glob('rras-git-boundary-*/evidence.json'))
assert len(files)==1
e=json.loads(files[0].read_text())
assert e['success'] and e['api_calls']==0 and len(e['cases'])==5
assert all(c['passed'] for c in e['cases'])
print('Dedicated-account Git boundary correction passed')
print(json.dumps(e,indent=2))
PY
printf 'RETAIN RUN_ID=%s WORK=%s\n' "$RUN_ID" "$WORK"
)
