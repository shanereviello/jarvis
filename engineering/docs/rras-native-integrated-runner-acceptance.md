# Integrated native task/wait/validation/export acceptance

2026-10-12. Continues [waiter acceptance](rras-native-waiter-acceptance.md); operator reported dedicated cgroup run b2f43f16082844749f5ee32ee69eb233 passed. Preserve that evidence. No installed release/profile, token, timer, old board, runtime allocation or fence changed here.

[probe_integrated_runner.py](../tools/rras_native/probe_integrated_runner.py) creates one fresh admitted disposable Git repo/native project/task, uses native claim/worktree/spawn/environment/logging with only coding replaced, and keeps the dispatching process alive while the bounded waiter observes the native worker and matching board run. Completion clears current_run_id in native Hermes: status reads therefore require matching latest run and refuse another current/latest run. The initial development failure exposed this normal transition; `/tmp/rras-integrated-success-20261012-01` remains retained. No automatic retries.

Three actual development cases passed with real board reads:

- Success: fake worker fixes add(a,b), validates and completes through native CLI; parent waits for exit, repeats validation and hash-verifies patch/log export.
- Crash: exit7 and native running status yield failure; failed validation and patch/log export are retained without closing the native run.
- Timeout: receipt records unverified termination/running status and no export. After writing that receipt, **fixture-only** cleanup checks direct-child birth identity and stops only its known fake worker, retaining a separate cleanup receipt and the still-running native record. No production cancellation claim.

[Development evidence](rras-native-integrated-runner-development-evidence.json) records UID1000, no dedicated cgroup and zero API calls. Status is now native, not simulated; coding remains deliberately fake. Source suite **46 passed**. Actual published inventory/hashes and Bash syntax passed. Production credentials, model compliance, model session references and paid execution remain untested. This entrypoint cannot run a real model worker; do not substitute an API key or convert the fake child manually.

Fresh candidate `/tmp/rras-integrated-review-20261012-01`; manifest SHA256 `b17ef32b5b7d3bcbd38f5fe4b58cbf3a53227306e0b067182908de4a971393c9`. Operator sidecar SHA256 `69587b00070f671328e952016de2bb42d90625cc6dac8a352bd604fb74ae7966`. [Repository script](../tools/rras_native/run_integrated_acceptance.sh).

Run once on server01:

```bash
(
set -euo pipefail
SCRIPT=/tmp/rras-integrated-review-20261012-01/operator-acceptance.sh
EXPECTED=69587b00070f671328e952016de2bb42d90625cc6dac8a352bd604fb74ae7966
test -f "$SCRIPT"
test ! -L "$SCRIPT"
printf '%s  %s\n' "$EXPECTED" "$SCRIPT" | sha256sum --check -
bash "$SCRIPT"
)
```

The script publishes only a fresh root-owned review and unique UID996 private WORK. It runs success/crash/timeout in three separate transient dedicated cgroups named from the printed UNIT prefix plus exact case suffix; each has PrivateNetwork, no capabilities, 45s max/5s stop timeout, 1GiB/128 tasks/one CPU. Each case has a fresh isolated native board/repo; no shared queue. A successful test of crash/timeout is not successful coding-task completion. All receipts, failed tests, patch exports and boards remain retained. Timeout cleanup never mutates lifecycle; its receipt must verify the known fake child stopped. Systemd bounds the cgroup on unexpected failure.

Stop on first failure. Return SAVE RUN_ID/WORK and full output. Do not republish an existing root review, rerun a failed block wholesale, clear native writer state, or delete old evidence. Only a confirmed-created exact still-active case unit may be stopped. Normal service completion collects units while retaining files; no destructive cleanup needed. Existing timer stays disabled.

After this gate passes, prepare the explicit real-token/one-paid-canary authorization package and actual model worker invocation with the same corrected profile, repository instruction contract, parent wait and validation/export path. No authorization for real-key access or paid calls is implied here. Portal controls remain the spending policy; application hard budget enforcement remains deferred.
