# Corrected profile and repository-instruction dispatch acceptance

2026-10-12. Continues [native CLI context acceptance](rras-native-cli-context-acceptance.md). Operator run 4ee4808bcc854078813effdf9f599f58 passed its 19 cases under UID996; preserve all evidence. That receipt's fake worker still had bfl in argv, so it did not accept the corrected dispatch configuration.

Updated probe accepts an explicit corrected profile, validates its provider/API mode/manual approvals before dispatch, copies it into a fresh fixture profile, and verifies actual worker argv is exactly kanban,skills and configuration bytes survive. It continues to test real native CLI task-body inspection, stale-run rejection, matching-run completion and evidence export inside the actual Codex sandbox. No MCP, API keys, model turns or installed profile edits.

Actual development run `/tmp/rras-native-dispatcher-iehni2kl` passed **21 checks**, using the actual installed native dispatcher with only the coding executable substituted. [Evidence](rras-native-corrected-profile-dispatch-evidence.json). Source suite **41 tests passed**; actual fresh candidate preflight and Bash syntax passed. This remains UID1000 development acceptance; actual model following, paid completion, timeout/cgroup failure recovery and credential-bearing native spawn remain pending.

Fresh review candidate `/tmp/rras-native-cli-context-review-20261012-03`; manifest SHA256 `b4a05415ec5ff1f406df02e55efd6916ada9cd3dac648130cf3a69df610fcec2`. Manifest covers updated probe, activity utility and corrected profile. Operator sidecar SHA256 `c85a0c98bb98b455b7f97d8c4441fa786f2f990dd43d147701e95fe9feaef4f5`. Old reviews/candidates remain untouched. Installed native-10 and real token unchanged.

## Next administrator block

Run once on server01:

```bash
(
set -euo pipefail
SCRIPT=/tmp/rras-native-cli-context-review-20261012-03/operator-acceptance.sh
EXPECTED=c85a0c98bb98b455b7f97d8c4441fa786f2f990dd43d147701e95fe9feaef4f5
test -f "$SCRIPT"
test ! -L "$SCRIPT"
printf '%s  %s\n' "$EXPECTED" "$SCRIPT" | sha256sum --check -
bash "$SCRIPT"
)
```

This publishes only a fresh root-owned probe/config review and one unique UID996 private fixture, then runs a bounded transient unit (PrivateNetwork, no capabilities, 120s maximum, 1GiB, 128 tasks, one CPU). It does not replace installed code/config or create a production coding task. The worker is explicitly fake; the CLI lifecycle operations and sandbox are real. Success requires all 21 cases, uid996 and verified fake-child stop. Save printed RUN_ID/WORK. Return output. No paid authorization is implied.

Stop at first failure; retain exact review, fixture, board, worktree, output and receipts. Do not rerun the entire block after root publication or delete old evidence. Stop only a confirmed-created exact active unit if necessary; no wildcard cleanup/fence release. Normal completion retains artifacts; no deletion is required.

After this combined dedicated-account check passes, continue bounded real-canary runner/waiter preparation and failure-path validation with corrected configuration and instruction metadata. A dispatcher returning is not worker termination. Real credential delivery to a native worker and a paid model turn still require their explicit remaining review gates; do not treat these fake-child tests as proving them. Portal limits remain the operator's spending policy; custom hard budget enforcement is deferred.
