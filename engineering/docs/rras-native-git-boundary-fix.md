# Git boundary fix for the first canary

2026-10-12. Preserve failed paid run36459f5e868b4211b7f0f021655d3f84 and all installed reviews. Progress evidence shows coding started, calc contains addition, no established quota error, and one read-only/exit128 failure. Its precise raw error target has not been extracted; Git commit failure is independently reproduced rather than asserted as the sole timeout cause.

[Model-free probe](../tools/rras_native/probe_git_metadata.py) reproduced commit exit128/read-only inside the actual Codex sandbox. A trial of extra Git roots did not resolve it; its failed evidence remains `/tmp/rras-git-boundary-ebindm1j`. No extra runtime launcher or broad Git authority is retained. The accepted correction keeps coding roots unchanged.

The reviewed instruction contract now tells the model to fix calc.py, preserve tests/instructions, run tests and complete via native CLI **without git add/commit**. After matching native completion, verified worker/cgroup termination and independent validation, the trusted UID996 runner stages only the regular calc.py change and creates a local synthetic RRAS Canary commit. It refuses unexpected status entries, modified control files, symlinks or secret-bearing patch/log content. Git hooks/fsmonitor/global config/signing are disabled for this explicit local commit. No push/merge/deploy. Native completion and successful RRAS validation/commit/export remain separately recorded gates; failed parent validation does not silently rewrite native lifecycle.

Four model-free development checks passed: coding sandbox commit refusal, sibling repository-code write refusal, app-server stopped, and successful trusted-parent validation/local commit. [Evidence](rras-native-git-boundary-evidence.json); source suite **62 tests passed**, including exact-file commit, extra-file refusal without staging and symlink refusal. All installed code remains unchanged. Another paid attempt is not authorized by the request to fix source.

## Latest verification and failed host attempt

Dedicated-account run `d5faa53e03744acea790c04b45f1909a` failed: sandbox commit returned 1 without the expected read-only marker. Sibling write denial, server shutdown and trusted-parent commit passed. This is **not acceptance passed**; retain its `/var/lib/rras-engineering/git-fix-d5faa53e03744acea790c04b45f1909a` and root review -01. The old probe omitted command output, so the precise failure remains unknown.

The revised probe first requires sandboxed `git rev-parse HEAD` to match the baseline, then requires an explicit index/lock write denial (read-only or permission denied). Unrelated errors, missing Git and author errors fail closed. Its bounded command outputs are retained only for this synthetic, credential-free fixture. Five development checks passed against installed Codex in `/tmp/rras-git-boundary-nphh105t`; **65 source tests passed**. These do not establish UID996 acceptance. The new review -02 preserves all old allocations and installed code.

## Sandbox fork failure and bounded correction

UID996 run `79a272dd52554fe394309c4b30dda9ad` failed before sandbox commands could execute: exit101, `failed to fork sandboxed command: Resource temporarily unavailable`. No Git containment acceptance passed. The previous sibling-denial assertion incorrectly accepted a generic startup failure; it now requires a successful Git read control and an explicit target-path write-denial error. Preserve this run and root review -02.

The fixture had TasksMax=32, unlike successful native App Server fixtures using 128. Review -03 raises only this transient fixture cap to **128**, retaining 512MiB, one CPU, private networking and 60s lifetime. Thread counts consume TasksMax too. The old receipt lacks pids-event evidence, so cap exhaustion is a hypothesis, not a proven diagnosis. The new receipt retains cgroup pids.max/pids.peak/pids.events when available. No host/daemon/installed-service policy changes. If forking still fails, stop and inspect these counters rather than expanding privileges.

All **67 source tests passed**; revised five-case development fixture passed at `/tmp/rras-git-boundary-1p2hfg8p`. That development run had unlimited pids and does not validate the UID996 bounded service. Actual bundle inventory, shell syntax and source parity passed.

## Dedicated-account acceptance

Fresh candidate `/tmp/rras-git-fix-review-20261012-03`, manifest SHA256 `3da2bd252cb66c37ae704d5d9bdbd1fdb5645f4ad6af9f3cfa6b8e2b2b9fc745`. Operator script SHA256 `04202e031fd3dae1506250ba6eb5d14ee781ea60e2f2a79e4ac170f349271d37`. Actual candidate inventory preflight and shell syntax passed.

```bash
(
set -euo pipefail
SCRIPT=/tmp/rras-git-fix-review-20261012-03/operator-acceptance.sh
EXPECTED=04202e031fd3dae1506250ba6eb5d14ee781ea60e2f2a79e4ac170f349271d37
test -f "$SCRIPT"
test ! -L "$SCRIPT"
printf '%s  %s\n' "$EXPECTED" "$SCRIPT" | sha256sum --check -
bash "$SCRIPT"
)
```

This publishes only a new root review, creates unique private UID996 WORK and runs one transient PrivateNetwork fixture with 60s maximum/5s stop, 512MiB/128 tasks/one CPU/no capabilities. It performs initialization/command execution only, no model turn or credential access. It uses its own Git repo; the failed canary's code/board remains untouched. Normal completion retains the review, repo and evidence; no deletion needed. Stop on first failure, preserve exact UNIT/WORK and return output. Do not rerun absent-only publication or clear writer state.

After acceptance, prepare a fresh paid-review candidate containing corrected instructions and trusted commit helper. Existing root review -03 still contains the old instruction contract and must not be used again. Another paid attempt requires explicit authorization after reviewing remaining evidence and portal usage; no new source/service installation or paid call occurred here.

## Dedicated-account acceptance passed

Operator run `d734e8c8a96e4e4ba6a530d63cc05766` passed all five cases under UID996, service exit0. Evidence retained at `/var/lib/rras-engineering/git-fix-d734e8c8a96e4e4ba6a530d63cc05766/rras-git-boundary-7z_4_ytv/evidence.json`. Git read succeeded, index.lock and sibling writes were explicitly read-only, server stopped and trusted parent validated/committed. pids.max=128, pids.events=max 0. This establishes the bounded model-free host fixture, not paid completion or production deployment.
