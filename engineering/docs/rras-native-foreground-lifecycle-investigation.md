# Native foreground lifecycle investigation

2026-10-05. One bounded diagnostic pass; stop here. Architecture remains [native-first](rras-native-first-architecture-review.md). Hermes owns lifecycle/worktrees/dispatch; Codex owns coding runtime; RRAS supplies thin admission/evidence/review. No new controller, daemon, watchdog, database or Docker path.

## 1. Observed problem

Earlier credential-free/no-platform `hermes gateway run` fixtures inside this agent's outer execution sandbox did not expose readiness in 40 seconds and needed SIGKILL after 15 seconds of SIGTERM grace. Thread traces showed an idle executor while asyncio was waiting. Those failed receipts remain unchanged.

The same pinned source/venv/config was tested outside that outer sandbox, as the operator user, in fresh private homes. It reached native `gateway_state=running`, with matching PID, no platforms and zero active agents. The first host-side stop occurred immediately after the state appeared; a second settled run waited two seconds before SIGTERM. Both exited promptly with native exit code **1**, not SIGKILL. The settled run observed readiness in **4.006 seconds**, SIGTERM shutdown in **0.314 seconds**, removed its PID file, and had no observed descendants before or after stop.

[Machine-readable evidence](rras-native-foreground-lifecycle-evidence.json) references the original settled receipt and its hash. Original scope `/tmp/rras-native-foreground-gpq75owk` contains home/state, gateway log and native exit diagnostics. The receipt's old `success=false` is retained: its obsolete classifier required exit code zero. The new assessment corrects that interpretation, not the original journal.

## 2. Root-cause evidence

Two independent issues caused the misleading result:

1. **Outer sandbox interfered with asyncio wakeups.** A bounded standard-library executor control instrumented the event loop's existing self-wakeup socket. Inside the outer sandbox, its `send` returned EPERM; outside it, no wakeup error occurred. Python's normal `_write_to_self` catches that error, leaving cross-thread callbacks without their usual wakeup. In native startup, `start_gateway` awaits executor-based MCP discovery (`gateway/run.py`, around 30607); a missing wakeup explains idle executor/thread traces and progress around signal delivery. Exact attribution to a particular outer sandbox rule was not investigated or changed. The host-side native lifecycle comparison establishes that the earlier delay is not a demonstrated Hermes no-platform lifecycle gap.
2. **The probe incorrectly required zero after external SIGTERM.** Pinned `gateway/run.py` around 30824 explicitly returns False after external signal-initiated shutdown without a planned restart, to let `Restart=on-failure` revive a gateway. `hermes_cli/gateway.py` around 5791 maps False to exit 1 after teardown. The settled fixture's native exit log records `asyncio.run.returned` with false followed by `gateway.exit_nonzero`, and its main log records SIGTERM shutdown. This is intended exit semantics, not a hanging finalizer.

No Hermes source change is required. `probe_foreground.py` now records signal timing, descendants, PID-file removal and shutdown observation; it accepts pinned external-SIGTERM codes 0/1 only after readiness and observed shutdown, without SIGKILL or remaining observed children. Readiness still precedes some cron/housekeeping wiring; the settled check guards against terminating at that immediate startup boundary. This is a model-free no-platform lifecycle result, not a claim that coding workers were present or their cgroup behavior was tested.

Optional Slack plugin import warned about missing aiohttp; it did not prevent readiness. Native SQLite DELETE-journal fallback remained active. No optional platform credentials or dependencies were added. Background native scheduler/keepalive threads shut down sufficiently for the CLI's normal hard-exit-after-teardown path; no external SIGKILL was needed. No configured MCP servers, cron jobs or coding tasks existed.

## 3. Native options evaluated

| Interface | Status at pinned 0.20.4 | Readiness/shutdown | Ownership implication |
|---|---|---|---|
| `hermes gateway run`, isolated home, zero messaging platforms | Supported foreground CLI | Host-side readiness and bounded SIGTERM teardown accepted; exit 1 is expected | Native embedded dispatcher is the supported persistent owner; actual worker cgroup acceptance remains pending |
| `hermes kanban dispatch --max 1 --json` | Supported one-pass CLI | Previous native API/default-spawn fixture passed; direct CLI help verified | Native detached child survives dispatcher exit outside systemd; accepted manual-first path, no promise of unattended ownership |
| `hermes kanban daemon --force` | Deprecated hidden escape hatch | Not executed | Rejected for production; not needed |
| Replacement RRAS dispatcher/supervisor | Outside selected architecture | Not built or tested | Rejected |

No alternate foreground owner is needed. No broader machine privilege is required by this finding: the successful invocation ran outside the *diagnostic agent's outer sandbox*, while preserving the intended Codex coding sandbox. This does not authorize production full-access coding tools or root execution.

## 4. Decision

**Native foreground gateway accepted for the demonstrated credential-free lifecycle (Outcome A: invocation/test-environment correction).** Run the host-native engineering owner directly under the future low-privilege identity, rather than inside this agent's restrictive diagnostic execution sandbox. Correct the probe's external-SIGTERM interpretation. Preserve native restart semantics; do not rewrite Hermes lifecycle to force exit zero.

This acceptance does not select or activate a production service. Before choosing systemd restart policy, distinguish explicit administrator stop from unexpected external SIGTERM; systemd's deliberate service stop does not trigger its ordinary restart behavior. Do not suppress all genuine exit-code-1 failures with an unqualified success override.

## 5. First canary consequence

**Manual one-pass native dispatch is sufficient for the first dedicated-UID canary**, provided actual dedicated-UID sandbox/authority gates and real session/tool/approval checks pass. Persistent unattended service ownership is not a prerequisite for that canary.

Sequence remains: RRAS admit → native Kanban task/worktree → operator invokes native one-pass dispatch → Codex bounded coding → RRAS export → human review. The operator must observe task completion/worker termination and retain task/run/log/patch evidence. The earlier fake-child test is not proof of authenticated model behavior. No paid canary is authorized or started by this checkpoint.

## 6. Later unattended Jarvis milestone

A separately reviewed native foreground engineering-only gateway can host the embedded dispatcher with its own home/board/profile and no copied messaging credentials. Still demonstrate actual dedicated-UID behavior, inherited coding sandbox/tool surface, fail-closed approvals, worker termination within the selected systemd cgroup, restart/recovery and native task submission from Jarvis. Keep the existing messaging gateway untouched. No custom RRAS scheduler or lifecycle protocol is justified by this investigation.

An upstream Hermes patch/upgrade is not currently required to solve the observed lifecycle problem. Reconsider only if actual dedicated-UID/cgroup/session tests establish a concrete native limitation; preserve manual dispatch meanwhile.

## 7. Updated next step and stop

Next separately authorized slice: finish the reviewed account/release provisioning and **dedicated-UID model-free acceptance** procedure, preserving manual one-pass dispatch as the first-canary entry point. Unattended cgroup ownership can be validated as its own later milestone. Reference [host acceptance preparation](rras-native-host-acceptance-preparation.md) for the prepared payload; its former foreground-blocker statement is superseded by this checkpoint, not its pending provisioning/credential gates.

Source validation: **26 focused RRAS native tests passed**, including rejection of SIGKILL, unobserved shutdown, unexpected children, and the pinned SIGTERM exit-code semantics. Syntax/diff checks pass. Earlier immutable review bundles are preserved; no deployment bundle was replaced or installed in this diagnostic pass.

Stopped after investigation and documentation. No accounts, installed units/releases, timer, live gateway, production records, fences, credentials, migrations, model turns or paid calls were changed. All runtime signals targeted only newly created fixture processes (and the bounded standard-library control); state/logs remain for review.
