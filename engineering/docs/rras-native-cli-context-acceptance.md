# Repository instructions and native CLI acceptance

2026-10-12. Operator approved the repository-instructions/native-CLI approach. Continues [context decision](rras-native-canary-context-decision.md) and [CLI credential acceptance](rras-native-cli-credential-acceptance.md). Dedicated sentinel delivery passed according to operator run 59324c06a5754bcd908504e752fd94a8; preserve all paths. No installed release, profile, secret, timer or runtime fence changed here.

## Implemented and demonstrated

[probe_dispatcher.py](../tools/rras_native/probe_dispatcher.py) now has an optional --codex-binary model-free lane. The disposable baseline includes AGENTS.md pointing to RRAS_TASK.md, explicit installed native show/complete commands, required task/run environment variables and no-publication instructions. These files persist in the native task worktree. Actual native project/task/worker lifecycle remains in Hermes; only coding is a holding fake child. The actual Hermes wire client executes native CLI operations through actual Codex command/exec with the board as its native extra writable root. No MCP, credentials or model turns are introduced.

Actual development acceptance: **19 checks passed**, including sandboxed native task-body inspection; stale run completion refused with task still running; matching run completion; instruction files preserved; native terminal state; fixture child and app-server stopped; hash-verified patch export. [Evidence](rras-native-cli-context-evidence.json), original root `/tmp/rras-native-dispatcher-vsgg75cr`. CLI response details are retained in native-cli-results.json there. Binding is still operator-attested, logs reported/unverified, database_indexed=false. This is UID1000 development acceptance, not UID996 acceptance or model instruction compliance.

First outer-sandbox attempt `/tmp/rras-native-dispatcher-ebixyatn` timed out on command/exec; its failed receipt and stopped-child result remain retained. Both successful runs outside the development session's outer sandbox used ordinary operator identity, no sudo or real key. This agrees with earlier outer-sandbox interference; do not count that failed attempt as passed.

Focused native source suite: **41 passed**. Current bundle manifest and operator sidecar hashes verified; Bash syntax and git diff --check passed. Real coding, instruction following, entitlement, cancellation and timeout recovery remain unproven; no paid invocation is provided by this fixture.

## Next dedicated-account block

Candidate `/tmp/rras-native-cli-context-review-20261012-02`; manifest SHA256 `090fa547c1ff407b5f64522efc45937df56e35ac1e31d3941c46db4878c98bbe`. Manifest covers updated probe and activity utility. Separate operator sidecar pin: `88efa4f3a3926397d2c3261c467f8216f4b7de44bfba7744e0f2695ffefcc2d1`. [Repository operator script](../tools/rras_native/run_native_cli_context_acceptance.sh).

Run on server01 once:

```bash
(
set -euo pipefail
SCRIPT=/tmp/rras-native-cli-context-review-20261012-02/operator-acceptance.sh
EXPECTED=88efa4f3a3926397d2c3261c467f8216f4b7de44bfba7744e0f2695ffefcc2d1
test -f "$SCRIPT"
test ! -L "$SCRIPT"
printf '%s  %s\n' "$EXPECTED" "$SCRIPT" | sha256sum --check -
bash "$SCRIPT"
)
```

The script publishes a fresh immutable root review, creates one unique UID996 private fixture parent, and starts one transient systemd service with PrivateNetwork, no capabilities, one-core/1GiB/128-task limits, RuntimeMaxSec=120 and TimeoutStopSec=10. It substitutes only the coding executable; no production task or credential. No persistent service, timer or old application changes. Printed SAVE RUN_ID/UNIT/WORK identifies its owned resources. Success requires uid996, all 19 cases, verified fake-child stop, no actual coding session and native_cli_in_codex_sandbox_tested=true. Existing dedicated_uid_tested/systemd_cgroup_tested fixture flags remain false because they do not independently certify identity or fault-injected cgroup recovery; the script's UID check and transient-unit receipt supply execution context only.

On any failure retain exact root review, WORK, output.log, JSON receipts, board and worktree. No overwrite/retry of an existing root review; return the failing stage for a resume procedure. Stop only a confirmed-created exact still-active unit if needed, never wildcard names. Normal completion collects the transient unit but retains files; no deletion or fence release is needed. The app-server is closed in finally and only the verified fake-child PID can be signaled by fixture cleanup. The service owner remains alive until child exit; this is bounded acceptance plumbing, not a new lifecycle daemon.

After this dedicated acceptance passes, finish the fresh paid-canary task/invocation with corrected provider/profile, reviewed instructions, validation and evidence collection. Keep real token provisioning and one paid canary separately authorized. Do not reuse the fake task IDs, completed board or fixture objective for inference. Portal limits remain operator-managed; no custom spending enforcement is asserted.

## Inventory preflight correction

Operator attempt using review -01 stopped at the initial candidate inventory assertion, before root review publication, SAVE RUN_ID or fixture creation. No acceptance cases ran. The separately pinned operator sidecar had been omitted from the allowed filename set. Review -02 explicitly includes that one regular non-symlink sidecar while still refusing unexpected entries; runtime source hashes and manifest pin are unchanged. Two regressions execute the actual preflight against a generated published-layout fixture and verify both valid layout and extra-file/symlink refusal. Focused suite 41 passed. Keep old review -01 unchanged; use only the new block above. No old-unit cleanup or record deletion is indicated by this preflight failure.
