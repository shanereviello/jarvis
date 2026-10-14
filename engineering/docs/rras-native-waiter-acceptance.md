# Bounded manual waiter acceptance

2026-10-12. Operator reported corrected-profile/native-CLI run 5a1f22f646734f3e8d22a638c2a913e1 passed under UID996; preserve its board/worktree/export. Continues [corrected dispatch acceptance](rras-native-corrected-profile-dispatch-acceptance.md). No installed release, service, token, timer or old record changed here.

## Source scope and evidence

[wait_worker.py](../tools/rras_native/wait_worker.py) is a bounded wait component, not a scheduler or lifecycle controller. Caller must own the spawned child and dedicated service cgroup. It checks direct parent/start identity, waits for process exit **and** an empty cgroup (including nested cgroups), and requires successful exit plus done status. Its NativeChild adapter accepts only a verified direct child returned by native spawn, not a journal/planned PID. Unknown ownership, PID ambiguity, a crash, missing completion, or timeout cannot produce success. It sends no signals, changes no lifecycle state, releases no writer ownership and performs no automatic retries.

[probe_wait_worker.py](../tools/rras_native/probe_wait_worker.py) tested four local scenarios: done before exit still waits; nonzero exit fails; zero exit without completion fails; timeout retains a JSON receipt with unverified termination. [Development evidence](rras-native-waiter-development-evidence.json) records UID1000, dedicated_cgroup_tested=false. Status callbacks in this fixture are deliberate **simulations**, not Hermes board reads. Owned Popen handles clean up only these test workers; this is not production cancellation. Native DB/waiter integration and validated patch export after a paid worker are not yet implemented by this component.

Five new source regressions cover foreign PID refusal, native PID exit-code preservation, a remaining descendant preventing stop verification, PID reuse refusal, and bounded timeout enforcement. Native source suite: **46 tests passed**. Actual published candidate preflight, manifest/file hashes, Bash syntax and diff checks passed. Fault-injected systemd death/recovery and authenticated cancellation remain separate untested scopes.

## Dedicated-cgroup operator check

Fresh candidate `/tmp/rras-waiter-review-20261012-01`; manifest SHA256 `e33830fb7b626d884b2aeae96d97f6e2a46fd16490b59a6d7d3d8660c40b7202`. Operator sidecar SHA256 `63a91b8003e7d9d72125642a71a7a9dabfce109732cba2be3ebec2ce7e3a1fc1`; [repository script](../tools/rras_native/run_waiter_acceptance.sh).

Run once on server01:

```bash
(
set -euo pipefail
SCRIPT=/tmp/rras-waiter-review-20261012-01/operator-acceptance.sh
EXPECTED=63a91b8003e7d9d72125642a71a7a9dabfce109732cba2be3ebec2ce7e3a1fc1
test -f "$SCRIPT"
test ! -L "$SCRIPT"
printf '%s  %s\n' "$EXPECTED" "$SCRIPT" | sha256sum --check -
bash "$SCRIPT"
)
```

The script validates actual published inventory (including its separately pinned sidecar), publishes an absent-only root-owned review and one unique private UID996 WORK, verifies an initially empty dedicated cgroup, and runs only harmless Python fixture workers in a transient service. It uses no native task/board or model. Limits: PrivateNetwork, no capabilities, 512MiB, 32 tasks, one CPU, 30s maximum, 5s stop timeout. The fifth case creates a real descendant that remains after leader exit; success requires the waiter refuse verified termination, then verify that this deliberately short-lived descendant naturally exits. A unified cgroup is required; unsupported/ambiguous layout fails closed rather than substituting PID-only checks.

Every ordinary case retains a separate JSON receipt **before** fixture cleanup; output.log and final evidence.json stay under printed WORK. The intentional timeout case is a successful *test of refusal*, not successful task completion. If a descendant remains, the harness reports failure; the service manager owns its bounded cgroup cleanup. No unrelated processes are signaled. Normal completion retains root review/evidence and collects only this transient unit; no deletion needed.

Stop on failure and return exact SAVE RUN_ID/UNIT/WORK and output. Do not rerun an absent-only publish block after root publication, adopt an old planned unit, recursively change ownership, clear fences or delete records. Only a confirmed-created exact active unit may be stopped for recovery. Existing reconciliation timer remains disabled; installed native-10 is untouched.

After this acceptance, wire the waiter to one fresh native task/run and read-only status, validation and export, then test that integrated runner without inference. Real API key delivery and one paid canary require separate authorization; no command in this document does either. Application hard budgets remain deferred to operator portal controls.
