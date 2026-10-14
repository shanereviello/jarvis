#!/usr/bin/env bash
(
set -euo pipefail
CANDIDATE=/tmp/rras-manual-runner-review-20261012-01
REVIEW=/opt/rras-manual-runner-review-20261012-01
RELEASE=/opt/rras-engineering/releases/native-10
ACCOUNT=jarvis-codex-engineering
RUN_ID=$(python3 -I -B -c 'import uuid;print(uuid.uuid4().hex)')
WORK=/var/lib/rras-engineering/manual-runner-$RUN_ID
UNIT=rras-manual-runner-$RUN_ID
sudo -v
test "$(hostname -s)" = server01
test "$(id -u "$ACCOUNT")" = 996
test "$(id -G "$ACCOUNT")" = 996
test "$(systemctl is-enabled jarvis-codex-reconcile.timer || true)" = disabled
test "$(systemctl is-active jarvis-codex-reconcile.service || true)" = inactive
python3 -I -B - "$CANDIDATE" <<'PY'
import hashlib,json,sys
from pathlib import Path
r=Path(sys.argv[1]);m=r/'manifest.json'
assert hashlib.sha256(m.read_bytes()).hexdigest()=='514c32610f6b6fe1f0396215e5ed1194b56e386c5df91a4b1c10cfb859344282'
f=json.loads(m.read_text())
assert {p.name for p in r.iterdir()}==set(f)|{'manifest.json','operator-acceptance.sh'}
sidecar=r/'operator-acceptance.sh'
assert sidecar.is_file() and not sidecar.is_symlink()
for n,h in f.items():
 p=r/n
 assert p.is_file() and not p.is_symlink()
 assert hashlib.sha256(p.read_bytes()).hexdigest()==h
PY
sudo test ! -e "$REVIEW"
sudo test ! -L "$REVIEW"
sudo install -d -o root -g root -m 0755 "$REVIEW"
for NAME in manual_runner.py probe_manual_runner.py native_task_cli.py activity.py wait_worker.py manual_paid_canary.py profile.json codex-config.toml manifest.json; do
 sudo install -o root -g root -m 0444 "$CANDIDATE/$NAME" "$REVIEW/$NAME"
done
sudo /usr/bin/python3 -I -B - "$REVIEW" <<'PY'
import hashlib,json,sys
from pathlib import Path
r=Path(sys.argv[1]);m=r/'manifest.json'
assert hashlib.sha256(m.read_bytes()).hexdigest()=='514c32610f6b6fe1f0396215e5ed1194b56e386c5df91a4b1c10cfb859344282'
for p in (r,*r.parents):
 s=p.stat();assert s.st_uid==0 and not s.st_mode & 0o022
runtime=Path('/opt/rras-engineering/releases/native-10/venv/bin/python')
for p in (runtime,*runtime.parents,runtime.resolve(strict=True),*runtime.resolve(strict=True).parents):
 s=p.stat();assert s.st_uid==0 and (p.is_symlink() or not s.st_mode & 0o022),p
for n,h in json.loads(m.read_text()).items():
 p=r/n;s=p.stat()
 assert not p.is_symlink() and s.st_uid==0 and not s.st_mode & 0o022
 assert hashlib.sha256(p.read_bytes()).hexdigest()==h
PY
sudo test ! -e "$WORK"
sudo test ! -L "$WORK"
test "$(systemctl show "$UNIT.service" -p LoadState --value)" = not-found
printf 'SAVE RUN_ID=%s UNIT=%s WORK=%s\n' "$RUN_ID" "$UNIT" "$WORK"
sudo install -d -o 996 -g 996 -m 0700 "$WORK"
sudo systemd-run --unit "$UNIT" --service-type=exec --wait --pipe --collect \
 -p User="$ACCOUNT" -p Group="$ACCOUNT" -p WorkingDirectory="$WORK" \
 -p UMask=0077 -p NoNewPrivileges=yes -p 'CapabilityBoundingSet=' \
 -p PrivateNetwork=yes -p KillMode=control-group -p RuntimeMaxSec=120 -p TimeoutStopSec=10 \
 -p MemoryMax=1G -p TasksMax=128 -p CPUQuota=100% \
 /usr/bin/env -i PATH=/usr/bin:/bin HOME="$WORK" PYTHONDONTWRITEBYTECODE=1 \
 "$RELEASE/venv/bin/python" -I -B "$REVIEW/probe_manual_runner.py" \
 --source "$RELEASE/hermes" --python "$RELEASE/venv/bin/python" --parent "$WORK" --profile "$REVIEW/profile.json" --codex-config "$REVIEW/codex-config.toml" --dedicated-cgroup \
 2>&1 | sudo tee "$WORK/output.log"
sudo /usr/bin/python3 -I -B - "$WORK" <<'PY'
import json,sys
from pathlib import Path
w=Path(sys.argv[1]);paths=list(w.glob('rras-manual-runner-*/evidence.json'))
assert len(paths)==1
p=paths[0];e=json.loads(p.read_text())
assert e['uid']==996 and e['success'] and e['dedicated_cgroup_tested']
assert e['api_calls']==0 and all(c['passed'] for c in e['cases'])
assert not e['actual_coding_session_tested']
assert len(e['cases'])==6
assert all(c['owned_fixture_cleanup'] for c in e['cases'])
print(p);print(json.dumps(e,indent=2))
PY
printf 'RETAIN RUN_ID=%s WORK=%s\n' "$RUN_ID" "$WORK"
)
