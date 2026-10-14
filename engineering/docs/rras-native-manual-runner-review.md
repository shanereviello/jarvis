# Manual admitted-repository runner — source review

2026-10-12. Continues the [successful paid canary](rras-native-first-paid-canary-review.md). Branch `phase5b/guarded-host-orchestration`, committed baseline `f0d8a6eaf016153708c3e46a32e204a93bd11a97`. Existing changes, installed native-10, legacy services/timer, failed task records and secrets are preserved.

## What is prepared

[manual_runner.py](../tools/rras_native/manual_runner.py) accepts a reviewed registry and bounded task request. It uses existing RRAS admission/export, native Hermes project/task/worktree/dispatch and the tested explicit-context CLI. The supported native `spawn_fn` callback publishes instructions and the actual claimed run **before** delegating to pinned Hermes `_default_spawn`; no race waiting for model startup, replacement worker implementation or independent lifecycle authority. That private native delegate is a version-pinned integration dependency, requiring retest on Hermes upgrades.

The callback appends task instructions to the assigned worktree's AGENTS.md and RRAS_TASK.md, preserving original bytes separately. After verified stop it checks both overlays unchanged, then restores exact originals; if modified, it preserves them and refuses validation/export. Parent repository instruction files are never changed. Overlays are retained in the private run record. Existing repository instructions remain applicable; only trusted internal repositories are admitted.

The request defines exact relative file paths, validation argv, timeouts and objective. No globs, Git metadata or top-level instruction-file edits. The repository must have a clean baseline, except native `.worktrees/` entries. Changes outside scope, symlinks and unexpected worker commits are refused. Scope is checked again after validation. The first general policy is **leave_uncommitted**: no automatic staging/commit of arbitrary files, push, merge or deployment. The prior canary's exact-file commit policy remains independently demonstrated; general commit approval is a later extension.

A stopped task receives independent operator-selected validation in a credential-free environment. Validation runs outside the coding sandbox under the same dedicated UID/systemd boundary; these are trusted reviewed commands, not model-selected commands. Timeouts or surviving validation descendants prevent export/success. No runner signals or closes native tasks automatically; installed unit teardown remains the process boundary. A native task can be done while RRAS validation fails: the receipt keeps that distinction.

Review exports now optionally include additional hash-verified artifacts. Generic exports carry `new-files.json` (base64 contents by relative path) and the exact request, alongside patch/status/logs. The existing activity export format is unchanged when no additional artifacts are requested. New-file evidence is essential: the original export path captured untracked names only. The receipt points to the captured artifact and its digest. Existing key bytes are screened in candidate evidence before export; this is not a general secret-detection claim. Hashes establish byte integrity, not protection from arbitrary same-UID host software.

Per-task private Hermes homes/boards follow the proven canary arrangement. Native claims apply within each board, not globally across private boards. Until a shared intake is installed, the operator must serialize the dedicated identity and must not launch another task while a previous unit/process remains. This slice does not implement authenticated intake, global arbitration, cancellation, recovery, database indexing, budgets, GUI or Jarvis submission.

## Task request contract

Example only — not an execution command; select a real clean repository, objective, paths and validation before any paid task:

```json
{
  "schema_version": 1,
  "task_id": "TASK-example",
  "repository_id": "approved-repository",
  "objective": "Describe the bounded change and acceptance criteria",
  "allowed_paths": ["src/example.py", "tests/test_example.py"],
  "validation_argv": ["/opt/rras-engineering/releases/native-10/venv/bin/python", "-B", "-m", "unittest", "-v"],
  "worker_timeout_seconds": 300,
  "validation_timeout_seconds": 60,
  "commit_policy": "leave_uncommitted"
}
```

Registry format is the existing [activity admission contract](../tools/rras_native/activity.py): canonical repository path, enabled flag, stable repository ID and Hermes project slug. Operator-reviewed inputs must be copied into the next immutable root review before execution; the model cannot select a repository or validation command. Source CLI requires UID996, an explicit one-task paid authorization and systemd-delivered credential. No paid invocation for this runner has been prepared or authorized yet.

## Verification and exact next operator block

**84 native source tests passed.** Six development native fixtures passed at `/tmp/rras-manual-runner-phi4knuu/evidence.json`: successful changed/new-file export; failed validation retaining export; unexpected changes refused; crash retaining failure evidence; worker timeout with unverified stop; validation timeout refusing export. Actual native dispatch/worktrees/CLI were used; coding child was fake. Development UID1000, cgroup verification false; no model calls/credentials. Failed/superseded development evidence was retained.

Focused regressions cover unsafe request paths, reserved controls, symlinks, unchanged/modified instruction restoration, existing-state preservation, real operator argv parsing and additional-artifact tamper detection. The full native source set passed after the artifact change; final fixture adds validation timeout. The entire legacy repository suite was not rerun.

Fresh candidate `/tmp/rras-manual-runner-review-20261012-01`, manifest SHA256 `514c32610f6b6fe1f0396215e5ed1194b56e386c5df91a4b1c10cfb859344282`. Operator script SHA256 `1cc1379e5804ebff5a2fac515b2d03080bcca4028149d067726acc63f9bdf082`. Actual inventory/source hashes, executable argument parsing and shell syntax checked.

```bash
(
set -euo pipefail
SCRIPT=/tmp/rras-manual-runner-review-20261012-01/operator-acceptance.sh
EXPECTED=1cc1379e5804ebff5a2fac515b2d03080bcca4028149d067726acc63f9bdf082
test -f "$SCRIPT"
test ! -L "$SCRIPT"
printf '%s  %s\n' "$EXPECTED" "$SCRIPT" | sha256sum --check -
bash "$SCRIPT"
)
```

The script publishes an absent-only root review `/opt/rras-manual-runner-review-20261012-01`, creates a unique private WORK, and runs all six cases under UID996 in one transient systemd unit: private network, no capabilities, 1GiB, 128tasks, one CPU, 120s maximum and 10s stop, control-group teardown. No real credentials or Codex/model session is used. Native CLI completion is real; this harness does not repeat the separately passed actual Codex sandbox acceptance. Dedicated-cgroup waiter/validation checks are enabled. Cleanup signals only exact birth-verified fixture children; teardown stops remaining owned unit processes. Worktrees, overlays, boards and evidence remain.

Stop on any failure; preserve printed UNIT/WORK and all root review files. Do not repeat absent-only publication, manually complete native tasks, remove overlays from live worktrees, or clear old fences. Partial publication does not modify installed releases/units; report the failed stage for an exact new review rather than overwriting it. No persistent service or timer is installed/activated by this block.

After UID996 acceptance, the operator must choose the first real repository/task/path list and validation command. Verify dedicated-UID access and review portal spending before preparing a separately authorized real-task invocation. Then install the reusable manual entry point in a new reviewed release; Jarvis intake should consume the same request/admission/evidence contract. Do not revive independent Phase5B controllers to accomplish this.

## Installed-identity host acceptance passed

Operator run `592ceb6681574b8cabf3411559831273`, unit `rras-manual-runner-592ceb6681574b8cabf3411559831273.service`, passed all six cases under UID996 with dedicated_cgroup_tested=true, service success/exit0, runtime19.913s. Retained evidence: `/var/lib/rras-engineering/manual-runner-592ceb6681574b8cabf3411559831273/rras-manual-runner-dnfhy0z7/evidence.json`. Exact fixture-child cleanup passed in each case. api_calls=0; actual_coding_session_tested=false. This proves the generic native orchestration/validation/evidence path in the bounded host unit, not a new model-backed real-repository run or reusable production installation. Existing releases, units, disabled timer, secrets and task records remain unchanged.

The next dependent inputs are the first repository (canonical server path or repository identity), bounded objective, admitted file paths and validation command. Verify a clean baseline and dedicated-UID access before creating its reviewed request; do not alter existing ownership or discard working changes to make admission pass. Paid execution needs separate explicit authorization after the concrete request is reviewed. The canary spending authorizations are consumed.
