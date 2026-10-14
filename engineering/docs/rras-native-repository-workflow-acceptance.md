# Disposable native repository workflow

2026-10-12. Continues [live session acceptance](rras-native-live-session-acceptance.md). Operator reported dedicated UID 996 live-session success, run ce0776389c3341e7aff7236451d923f8. Retain its records.

Updated [probe_dispatcher.py](../tools/rras_native/probe_dispatcher.py) admits the disposable repository before dispatch, retains a triage-only manual task preview, supports an explicit private fixture parent, and verifies content-addressed exported artifacts with an explicit dispatcher log. It uses actual native project, task, claim, worktree, spawn, concurrency, completion and run bookkeeping. Only the coding executable is substituted with a fake child; the fake edit is deliberately not model-backed validation.

Development run `/tmp/rras-native-dispatcher-71vgj93m` passed 13 checks with a retained native board, Git worktree, patch, task/run binding and local index. [Evidence](rras-native-repository-workflow-development-evidence.json). Binding remains operator-attested, logs reported/unverified, and database_indexed=false. Focused source suite: 33 passed. No production credentials, migrations, timer, installed code or records modified. Native SQLite selected its DELETE fallback; no Hermes/runtime upgrade was performed.

Dedicated-account run is pending interactive sudo authentication. Run this block on server01 once. New root-owned review is separate from native-10; no installed release is updated. Each fixture gets a unique directory; no cleanup deletes records.

```bash
(
set -euo pipefail
CANDIDATE=/tmp/rras-repository-review-20261012-01
REVIEW=/opt/rras-repository-review-20261012-01
RELEASE=/opt/rras-engineering/releases/native-10
ACCOUNT=jarvis-codex-engineering
RUN_ID=$(python3 -I -B -c 'import uuid;print(uuid.uuid4().hex)')
WORK=/var/lib/rras-engineering/repository-acceptance-$RUN_ID
UNIT=rras-repository-acceptance-$RUN_ID
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
assert hashlib.sha256(m.read_bytes()).hexdigest()=='71250491f38e799e2ec1ad1982740258ca9848dfb324470eee160b8976079981'
f=json.loads(m.read_text())
assert {p.name for p in r.iterdir()}==set(f)|{'manifest.json'}
for n,h in f.items():
 p=r/n
 assert p.is_file() and not p.is_symlink()
 assert hashlib.sha256(p.read_bytes()).hexdigest()==h
PY
sudo test ! -e "$REVIEW"
sudo test ! -L "$REVIEW"
sudo install -d -o root -g root -m 0755 "$REVIEW"
for NAME in probe_dispatcher.py activity.py manifest.json; do
 sudo install -o root -g root -m 0444 "$CANDIDATE/$NAME" "$REVIEW/$NAME"
done
sudo /usr/bin/python3 -I -B - "$REVIEW" <<'PY'
import hashlib,json,sys
from pathlib import Path
r=Path(sys.argv[1]);m=r/'manifest.json'
assert hashlib.sha256(m.read_bytes()).hexdigest()=='71250491f38e799e2ec1ad1982740258ca9848dfb324470eee160b8976079981'
for p in (r,*r.parents):
 s=p.stat();assert s.st_uid==0 and not s.st_mode & 0o022
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
 -p KillMode=control-group -p RuntimeMaxSec=90 -p TimeoutStopSec=10 \
 -p MemoryMax=1G -p TasksMax=128 -p CPUQuota=100% \
 /usr/bin/env -i PATH=/usr/bin:/bin HOME="$WORK" PYTHONDONTWRITEBYTECODE=1 \
 "$RELEASE/venv/bin/python" -I -B "$REVIEW/probe_dispatcher.py" \
 --source "$RELEASE/hermes" --python "$RELEASE/venv/bin/python" --fixture-parent "$WORK" \
 2>&1 | sudo tee "$WORK/output.log"
sudo /usr/bin/python3 -I -B - "$WORK" <<'PY'
import json,sys
from pathlib import Path
w=Path(sys.argv[1]);paths=list(w.glob('rras-native-dispatcher-*/evidence.json'))
assert len(paths)==1
p=paths[0];e=json.loads(p.read_text())
assert e['uid']==996 and e['success'] and e['fixture_child_stopped']
assert e['api_calls']==0 and all(c['passed'] for c in e['cases'])
assert not e['actual_coding_session_tested']
print(p);print(json.dumps(e,indent=2))
PY
printf 'RETAIN RUN_ID=%s WORK=%s\n' "$RUN_ID" "$WORK"
)
```

On failure retain exact WORK/unit/review. Do not republish an existing review or rerun the whole block. A successful fake-child run does not authorize a real dispatch or certify cancellation/worker death. Stop only a confirmed-created exact active transient unit if needed; preserve native worktrees and records. Source fixture cleanup signals only its verified fake child. Systemd's bound limits the fixture lifetime.

## Manual coding command preparation

The fixture retains `manual-task-preview.json`: the exact native create argv, including project mapping, admitted baseline, idempotency key and triage. It is review-only and must not be executed against the completed fake-task board. A real canary requires a fresh admitted record/project, preserved worktree and verified profile/PATH/CODEX_HOME. Do not reuse fixture IDs or issue a board-wide dispatch against an existing queue. Prepare the final command with those fresh native IDs after dedicated acceptance and credential review, then obtain separate paid-canary authorization. Merge/push/deployment remain human-controlled. No custom scheduler or budget broker is introduced.
