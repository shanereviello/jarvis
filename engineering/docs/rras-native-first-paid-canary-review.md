# First paid canary: review package, not execution authorization

2026-10-12. Native integrated success/crash/timeout acceptance passed according to operator run b5094f76b800419ea9d9e8611be44c5f. Preserve all boards/worktrees/receipts. Installed release, profiles, timer and real key untouched in this preparation.

## Concrete proposed task

One fresh disposable native project/board/task/worktree under a new `/var/lib/rras-engineering` allocation. Fix only calc.py's add(a,b), preserve the baseline test/instruction files, run the supplied unittest, commit locally with explicitly synthetic RRAS Canary fixture identity, and complete via native Hermes CLI with the assigned task/run. Parent independently waits for exit and empty cgroup, repeats validation, requires a clean changed commit, preserves native references, and exports patch/validation/worker log hashes. No push, merge, deploy or automatic retries.

Use installed Hermes/Codex/Python pins and corrected openai-api/codex_app_server profile with exactly kanban/skills, bfl disabled, optional scanner download disabled, manual approvals, and no MCP. Codex remains network-off for coding tools, while its API control plane requires networking: **the real service must not use the sentinel fixture's PrivateNetwork=yes**. Dedicated UID996 remains separate from operator/Hermes/supervisor identities. Service limits proposed: one CPU, 1GiB, 128 tasks, 360s runtime/10s stop; waiter deadline300s. A task can make multiple internal model requests; one task is not one API request.

Real entrypoint [manual_paid_canary.py](../tools/rras_native/manual_paid_canary.py) requires --authorize-one-paid-task and UID996 before credential access. It accepts only a private regular no-symlink credential delivered through CREDENTIALS_DIRECTORY. It maps the selected dedicated API Platform key to OPENAI_API_KEY and RRAS_OPENAI_API_KEY, never argv/config/receipt. Native worker and its legitimate model runtime can access that provider credential; this is not adversarial protection from the model itself. Existing source location is `/srv/jarvis-codex/secrets/openai_api_key`; not inspected/read here. Root source ownership/mode/ancestor metadata and dedicated-project identity must be verified before authorized use, preserving /srv ownership and all existing files. Do not substitute personal Codex auth.

[Integrated implementation](../tools/rras_native/probe_integrated_runner.py) takes the real native spawn branch only when explicitly called by that paid entrypoint. Failure/timeout retains evidence and native state, performs no PID cleanup or lifecycle mutation, and lets the dedicated unit's KillMode=control-group stop remaining children. The timeout receipt does not certify that later stop; verify unit termination before any recovery. Exact key bytes in private worker/validation logs or the patch cause export refusal; raw native logs stay private and must not be pasted. This is a limited exact-byte guard, not general secret certification. Session ID/file references are retained when native storage exposes them, with API call count unknown rather than falsely zero.

## Costs and remaining authorization

Model candidate gpt-5.4; actual entitlement remains unverified and the first provider failure must stop without retry/fallback. Custom hard task/daily/month budget enforcement remains explicitly deferred. Operator API portal controls are the selected spending policy; their actual configuration has not been inspected. Time/resource bounds do not guarantee a $5 task maximum. No paid call is authorized by the previous model-free acceptance.

After the sentinel gate below, request explicit approval to read/use the existing dedicated API Platform key for **one** bounded paid canary, with these limits and retention behavior. Confirm that the file belongs to the intended service/project and portal limits are set. Do not run the paid entrypoint before that approval. A reusable deployment service and unattended Jarvis dispatch remain later milestones.

## Final sentinel handoff gate

Development fixture `/tmp/rras-native-handoff-development-20261012-02` passed native spawn, matching key-name delivery, actual App Server environment-helper preservation, private Codex config, completion/wait/validation/export. [Evidence](rras-native-credential-handoff-development-evidence.json) is UID1000/fake coding, not real-token or systemd acceptance. The production loader has unit tests with harmless bytes. **50 source tests passed**, including actual generated operator argv parsing, private credential/directory/symlink refusal. No inference.

Fresh candidate `/tmp/rras-canary-review-20261012-02`; manifest SHA256 `7edf81ed5221221444f25dbb4a5692f4a62ba1daf94440459692f4a1400a5a73`. It includes both sentinel probe and paid source for review, but the operator script below invokes only the sentinel probe, whose fixed-byte check rejects production credentials. Separately pinned script SHA256 `9bda4ea39630843d2745e7f06cf2782e2890e794e73abada121f090b68a0fd9d`. Root review destination is absent-only `/opt/rras-canary-review-20261012-02`; installed native-10 is not updated.

Run only this model-free block on server01:

```bash
(
set -euo pipefail
SCRIPT=/tmp/rras-canary-review-20261012-02/operator-acceptance.sh
EXPECTED=9bda4ea39630843d2745e7f06cf2782e2890e794e73abada121f090b68a0fd9d
test -f "$SCRIPT"
test ! -L "$SCRIPT"
printf '%s  %s\n' "$EXPECTED" "$SCRIPT" | sha256sum --check -
bash "$SCRIPT"
)
```

It verifies hashes/ownership, publishes fresh immutable code, creates unique root-owned harmless source/private UID996 allocation, and runs one bounded PrivateNetwork sentinel unit with LoadCredential. The fixed sentinel passes through the actual production credential loader, then native spawn and actual App Server environment helper, and results retain booleans only. It never invokes manual_paid_canary.py or reads the existing real key. Return saved RUN_ID and output. The separately tested original-source unreadability scope remains in earlier dedicated credential acceptance.

Stop on any failure; retain review/source/work/receipt/log paths. Never overwrite old candidates or rerun the entire absent-only publish block after a partial installation. Only confirmed-created exact active units may be stopped. No deletion, recursive ownership repair, timer activation or fence release. After this gate, the next action is explicit paid authorization and a separately supplied operator invocation with all variables defined; this document itself contains no executable paid command.

## Operator authorization received

Operator explicitly approved one paid canary and confirmed the dedicated project/portal policy after sentinel run b564ecb8ef2a44b9a85b6614994eca3a passed under UID996. This authorization persists; do not ask again merely because preflight/sudo failed before execution. No paid run has started in this source pass: sudo -n required a password.

Exact authorized invocation: [run_authorized_paid_canary.sh](../tools/rras_native/run_authorized_paid_canary.sh), prepared copy `/tmp/rras-paid-invocation-20261012-01.sh`, SHA256 `28623d4c236d500be0b3cdaed9ef95d185fc8e15d6ac0a7c072b08cb95725c7c`. It verifies the installed root review manifest and all source hashes, checks **metadata only** on the existing key and ancestors (root/private/non-writable), preserves all ownership, then uses LoadCredential for one new transient native worker. Any key/ancestor trust assertion fails before reading its bytes or starting a task. Do not repair that by chowning /srv; report the failed assertion for a concrete plan.

Run once on server01:

```bash
(
set -euo pipefail
SCRIPT=/tmp/rras-paid-invocation-20261012-01.sh
EXPECTED=28623d4c236d500be0b3cdaed9ef95d185fc8e15d6ac0a7c072b08cb95725c7c
test -f "$SCRIPT"
test ! -L "$SCRIPT"
printf '%s  %s\n' "$EXPECTED" "$SCRIPT" | sha256sum --check -
bash "$SCRIPT"
)
```

**This block is paid execution**, unlike earlier fixtures. Save PAID RUN_ID/UNIT/WORK. Stop at the first failure and do not rerun after a service/model worker has started. Return only operator-output and safe evidence summary; never paste the credential or raw native worker logs. Timeout/failure retains native board status and evidence. Systemd owns eventual cgroup shutdown; do not clear claims merely because the parent exited. Final evidence must independently satisfy wait, validation and export; successful unit exit alone is insufficient. A missing model/session reference is reported as a canary gap, not fabricated. Persistent services/timer/merge/deploy remain untouched.

Focused suite: 51 passed including actual generated paid argv parsed by the real entrypoint parser without executing its credential loader. Bash syntax/diff checks passed. Real-key metadata/preflight and model behavior remain operator-host work; model entitlement and actual spend are not inferred from sentinel results.

## Credential ownership preflight stopped before execution

Operator's invocation -01 failed at the key-source root/private assertion before SAVE PAID RUN_ID, key byte access or service creation. Metadata inspection shows original key owner UID1000, mode0600; /srv UID1000/mode0755, jarvis-codex and secrets UID1000/mode0700. Preserve these directories, original key and all applications. Do not chown /srv or silently weaken the paid source trust check.

Prepare a fresh root-owned copy under `/etc/rras-canary-credentials-20261012-01/openai_api_key`. This is the already approved dedicated project key, not a new credential or personal login. The operator-only install/cmp operations read bytes without printing them. Directory0700/file0600 and absence-only checks protect the new source. Existing authorization remains unconsumed: no paid task started.

```bash
(
set -euo pipefail
ORIGINAL=/srv/jarvis-codex/secrets/openai_api_key
SECRET_DIR=/etc/rras-canary-credentials-20261012-01
DESTINATION="$SECRET_DIR/openai_api_key"
sudo -v
sudo /usr/bin/python3 -I -B - "$ORIGINAL" <<'PY'
import stat,sys
from pathlib import Path
p=Path(sys.argv[1]);s=p.stat()
assert not p.is_symlink() and p.resolve()==p
assert stat.S_ISREG(s.st_mode) and s.st_uid==1000 and not s.st_mode & 0o077
for p in (Path('/etc'),Path('/')):
 s=p.stat();assert s.st_uid==0 and not s.st_mode & 0o022
print('Original metadata and new source ancestors verified; no key printed')
PY
sudo test ! -e "$SECRET_DIR"
sudo test ! -L "$SECRET_DIR"
sudo install -d -o root -g root -m 0700 "$SECRET_DIR"
sudo install -o root -g root -m 0600 "$ORIGINAL" "$DESTINATION"
sudo cmp -s "$ORIGINAL" "$DESTINATION"
echo 'Root-owned credential copy verified; original unchanged'
)
```

Stop on a failed copy or comparison; preserve the new directory and do not overwrite/repeat the block. Return the failed stage for exact recovery. Updated paid invocation copy `/tmp/rras-paid-invocation-20261012-02.sh` SHA256 `a154c94db3df7f771cfbc6a77dcd3bac2554c7ba6727418544305890c7b2f4aa` uses only the new source. Old invocation -01 remains retained and superseded. Five focused paid-gate tests and Bash/diff checks passed for this path-only update. All runtime code pins remain unchanged.

After copy success, use the same hash-verified invocation block above with SCRIPT ending -02.sh and EXPECTED set to the new digest. This is the authorized first paid execution, not an automatic retry of an earlier model attempt. Keep no-retry rules after worker start. No installed service/release/timer changed.

## Early paid-launch wiring failure and absent-worker recovery

Operator run 35478ebd54c94a138288157ce695d441 exited1 in 432ms with ValueError. Reviewed source showed the paid entrypoint called the shared function without paid=True. The shared function therefore selected fixture mode and rejected the real token before creating a repository, loading native Hermes modules, initializing a board or spawning a worker. The credential loader had already read the delivered copy; do not claim the key was never accessed. No model request is made by this early code path, but confirm the actual failed allocation before another launch.

The entrypoint now explicitly passes paid=True; the shared function refuses case=paid without that flag before creating state. A regression executes the actual entrypoint body with a harmless credential/provider stub and checks the paid keyword, rather than merely parsing its arguments. **52 source tests passed**, fresh source inventory/hash checks and recovery-command Bash syntax passed. No model call or privileged recovery executed in this source pass.

Keep root review -02, failed WORK and root-owned credential copy unchanged. New candidate `/tmp/rras-canary-review-20261012-03`, manifest SHA256 `f426659105840dc66144052634857dbc68a5e51c43126560f5a3a4ad39bfdc88`. Updated operator command `/tmp/rras-paid-invocation-20261012-03.sh`, SHA256 `f8d78e15e0f5f46fa40f9489c8e10c7b85e3d99b1bd7f28ac4fed706e298c9fd`.

The new command checks the old exact unit inactive/failed, requires no live dedicated-UID processes, and verifies the old allocation contains only its initial profile and operator-output.log, with no repository/native DB/worker receipt. Any additional record or ambiguity stops dependent work; no deletion, claim release or automatic adoption. It then publishes a fresh immutable root review -03 and uses the existing root credential copy for a fresh single paid attempt under the authorization already given. No old source is overwritten. If another model worker actually starts, stop at its first failure and do not automatically rerun.

Run the same hash-verified shell block with SCRIPT `/tmp/rras-paid-invocation-20261012-03.sh` and EXPECTED set to the digest above. This command combines reviewed recovery checks and the paid launch; it is not a model-free fixture. Do not repeat credential copying or earlier publish blocks. Preserve all printed PAID RUN_ID/UNIT/WORK paths, and return only safe operator output rather than raw native logs/key.

## Real canary timed out; do not rerun

Operator run 36459f5e868b4211b7f0f021655d3f84 spawned native task t_630b3df3/run1 under UID996 with real credential access. Waiter timed out after300s with Hermes/Codex PIDs still present; no validation/export occurred and native running state was retained. Unit exited1 after5min4.316s. Subsequent read-only host inspection found exact unit not-found/inactive/dead with empty ControlGroup and no dedicated-UID processes. Thus current host termination is verified independently of the earlier timeout receipt; do not edit that receipt or close the board task automatically.

No success, model response, charge amount or request count is established (api_calls=null). The one authorized model-backed attempt has run; no automatic retry or another paid attempt. Preserve WORK `/var/lib/rras-engineering/paid-canary-36459f5e868b4211b7f0f021655d3f84`, native board/worktree, private logs and session files. Next step is read-only diagnosis via fixed metadata/event/error marker counts, not raw log publication or real-key inspection. The SQLite fallback warning alone does not identify the cause. No installed units/releases/timer or native ownership was modified.

## Git commit boundary correction

Progress diagnostic did not establish quota failure; model coding and addition were present. Commit exit128/read-only was independently reproduced model-free. [Git boundary fix](rras-native-git-boundary-fix.md) keeps sandbox roots unchanged and moves an exact calc.py local commit to the trusted runner after verified stop and passing validation. Source suite67 passed; dedicated model-free acceptance passed in run d734e8c8a96e4e4ba6a530d63cc05766. Do not rerun old paid-review -03 instructions or launch another paid model task without new authorization. Preserve the first real attempt's evidence and native task.

## Corrected candidate for a second paid attempt — awaiting authorization

Model-free UID996 Git acceptance passed all five cases (see linked Git review). New candidate `/tmp/rras-canary-review-20261012-04`, manifest SHA256 `c90e775db0d9d19c7e5d777c7d64f33c1f9cf8fb4f85ad429e98d63296c8d37d`. Prepared invocation `/tmp/rras-paid-invocation-20261012-04.sh`, SHA256 `b4adffd7893f3449dbea0f930beb90e902aa096ed038e3dad23f6706b7c56242`. These are source candidates only; installed reviews/releases remain unchanged.

The candidate uses unchanged reviewed profile and Codex config with current source. Its task forbids sandbox Git staging/commit; the trusted runner commits only calc.py after matching native completion, verified stop, independent tests and control-file checks. Existing bounds remain 300s waiter/360s systemd, 1GiB/128 tasks/one CPU, no capabilities; coding network off, API control-plane network allowed. Existing root-owned API project key is delivered through systemd. No extra writable Git roots or privileges.

The invocation requires explicit `RRAS_AUTHORIZE_ONE_PAID_TASK=reviewed-canary-20261012-04`, checks the retained exact timeout receipt and inactive old unit, rejects any live engineering-UID process, verifies candidate and protected credential metadata, then publishes an absent-only fresh root review and launches exactly one new task. It does not alter old lifecycle/fences or read credentials during metadata preflight. Do not run until another paid attempt is explicitly authorized and operator portal usage is reviewed. Previous spend/request count remain unknown; runtime limits are not dollar caps. On any failure retain receipt and worktree; no automatic retry.

## Second paid attempt: validated code, incomplete native lifecycle

Operator run `56c1a14547d441c0931336a437318fd3` (task `t_2563a5dd`, run1) exited after29.401s. Worker exit0 and verified stop; native task remained running, so waiter outcome failed. Independent tests passed (validation_exit=0), and export `c1bd28c77905f3cbbae3bcb360df7f430b0f8bfc3c6109fd850687136a8d4dff` was retained. No success or commit is claimed: trusted commit requires successful matching native completion. database_indexed=false; request count/spend unknown. Preserve the task, workspace, receipt, export and root review -04. Authorization for the additional attempt has been used; no automatic paid retry.

Next gate is read-only classification of native show/complete commands and correlated tool results. No lifecycle repair is authorized implicitly. A new diagnostic emits only operation/boolean flags and exit codes, never raw commands, keys or tool output; absence means no observed command in the bounded scan, not proof it never ran. Source progress inspection now derives the worktree from the retained receipt rather than assuming the first paid task ID.

Prepared diagnostic `/tmp/rras-native-completion-diagnosis-20261012-01.py`, SHA256 `e022f9e2245430485c936da07c8d8cc5d1ad5f4db91988f1423c3e9b77a3d573`. Execute with isolated system Python and the fixed WORK path; it makes no API calls and changes no state.

### First completion diagnosis

Operator sanitized scan of second paid session observed one native-module `kanban show` using the task variable, exit1, with no complete command observed. Its result did not match the initial missing-module/write-denial/run-mismatch/locked categories. This does not yet establish the cause or justify changing lifecycle. The model-free acceptance used explicit command/exec argv; model-generated shell invocation is a different path and remains to be reconciled.

Expanded allowlisted diagnostic `/tmp/rras-native-completion-diagnosis-20261012-02.py`, SHA256 `a8cae6ca87ec1b343ee11c9b3fd5764acf45f485f5087b47a565abe385a6aebb`, classifies task-not-found, database-open/read-only, CLI usage, fork failure and fixed exception names without exposing arguments or exception messages. Preserve the native task and exported patch. Further paid execution is not authorized.

### Unclassified show failure: shell guard investigation

Expanded diagnostic -02 still found no CLI exception/error category. Cause remains unresolved. Do not invent a completion fix or close the existing task. Model-free native command/exec with synthetic task/run/board variables passed both bash -c and bash -lc presence guards at `/tmp/rras-shell-context-z5vb9mns`; server stopped, api_calls=0. This tests only development command/exec, not model-generated tool execution or the retained UID996 run.

Diagnostic -03 adds fixed command-structure booleans (presence guard, exit1, && chain, explicit nonlogin request), empty-output-body detection and a missing-task-context marker. It still prints no raw commands/output or arbitrary values. Candidate `/tmp/rras-native-completion-diagnosis-20261012-03.py`, SHA256 `56735f01c84482e6744f8bf1182518e363475ad0c85ce11f0e436656f0806743`. Five focused diagnostic regressions passed; whitespace check passed.

Official [Codex configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference) documents shell environment inheritance/filtering and explicit values; it does not establish the actual cause in this retained run. No environment-policy change is made based on speculation.

## Explicit task context: source correction and model-free acceptance candidate

Diagnostic -03 observed a task-variable presence guard, && chain, exit1 and an empty output body. This strongly suggests the model-generated shell stopped before native show; exact guard evaluation is not independently measured. The direct command/exec probes did not establish that model shell tools receive the same variables. Do not claim the precise environment-loss mechanism is proved.

The smallest correction removes inherited shell variables from the instruction contract. The existing native dispatcher still owns task/run/spawn/completion. After native spawn, the trusted runner atomically publishes a private0400 context outside coding writable roots, recording the actual task/run, private profile/board and pinned native-10 Python. Repository instructions invoke `native_task_cli.py --context <assigned path> show` and, after tests, `complete --result ...`; if context is not yet ready, wait at most10s then stop. Context creation does not overwrite. The bridge admits only those two native operations, supplies exact identity to the unchanged native CLI in a credential-free environment, and relies on native stale-run enforcement. It has no scheduler, worker ownership, cancellation, retry or paid model logic. Source installation must include this helper alongside the runner.

This small custom bridge addresses an observed integration failure at the model-shell boundary; cost is one narrowly scoped file, context publication and focused tests. It does not introduce a stronger custom orchestration system. UID996, Git sandbox, worker stop/validation/commit/export and human merge/deployment gates remain unchanged. Same-UID host processes remain within the trusted single-operator boundary; mode0400 alone does not protect against arbitrary same-UID host code.

Development acceptance `/tmp/rras-native-dispatcher-_bbl9ni6/evidence.json` passed **23 cases**: native dispatch/worktree, sandbox native show with inherited variables deliberately cleared, explicit context write denial, stale-run refusal, matching native completion, server/child stop and hash-verified export. No credentials/models/API calls; development UID1000, not installed UID996 acceptance. Two earlier development wrapper attempts failed while testing root ownership in the managed filesystem view (root files appear UID65534); their temporary evidence was preserved. The final bridge accepts only the exact reviewed native-10 Python spelling; the operator preflight verifies its root-owned installation in the actual host view.

Fresh candidate `/tmp/rras-explicit-context-review-20261012-01`, manifest SHA256 `d477d39be2bb1dc5636089fc28d7a7678110b90e35272db9173688d38c4bde99`; operator script SHA256 `cc98255f093cf9b8f071132573b67bd4063d46cb3575202be37846d3a0323006`. It publishes only a fresh root review and runs a unique disposable UID996 transient unit, private network, 1GiB/128tasks/one CPU/120s maximum/10s stop. Native coding child is fake; actual Codex sandbox CLI execution is real. It cannot access real credentials or make model calls. Preserve all failed paid task state and installed releases. Stop on failure and return retained evidence; do not republish over existing reviews or retry paid execution.

## UID996 explicit-context acceptance passed; next paid candidate prepared

Operator run `ac11e72e34c146d490b6ddb823815f44` passed all23 cases in13.122s, service exit0. Evidence remains `/var/lib/rras-engineering/explicit-context-ac11e72e34c146d490b6ddb823815f44/rras-native-dispatcher-_dr_dry1/evidence.json`. uid=996 and the operator transient-unit record establish dedicated host execution. Historical dedicated_uid_tested/systemd_cgroup_tested=false fields remain unchanged: the generic probe does not independently attest them. Coding child was fake; native dispatch, real Codex sandbox CLI, explicit-context completion/stale rejection and export were exercised model-free.

Fresh paid candidate `/tmp/rras-canary-review-20261012-05`, manifest SHA256 `f272364f9dec3c19f635f1b702a083e6f1be33512efb81ea6636c13d50a763d6`. Prepared invocation `/tmp/rras-paid-invocation-20261012-05.sh`, SHA256 `3b3f3114ec7a0076eef94e9d43392909eb9708e34099b86b17db890a3d8f1848`. It includes `native_task_cli.py` beside the runner; profile, model pin and Codex configuration are unchanged. Explicit-context instructions replace the failed inherited-variable contract. Root installation trust remains checked before the context bridge uses the pinned native-10 Python.

Invocation guard: `RRAS_AUTHORIZE_ONE_PAID_TASK=reviewed-canary-20261012-05`. It verifies the exact second paid failure receipt (native task t_2563a5dd/run1, clean worker exit/verified stop, validation0 and retained export), inactive old unit and no live dedicated-UID processes before absent-only publication and one new paid run. It does not mutate either previous task or repair its native lifecycle. Limits remain 300s waiter/360s unit, 1GiB/128tasks/one CPU. No release/unit/timer activation or production migration.

Both previous paid authorizations are consumed; **another paid attempt requires explicit authorization**. Prior spend/request counts remain unknown; operator portal policy remains the spending control. Do not use old invocations -03/-04 or overwrite published reviews. Candidate inventory/source parity and shell syntax passed; focused source checks cover paid argv/entrypoint, credential gate, explicit context and commit refusal.

## First complete paid canary passed

Operator run `bd70070307cb45dd8ccc9890c888afef`, native task `t_2b63fff8`/run1, passed in33.767s under UID996. Native status done, worker exit0 and verified stop, validation_exit=0, export `874002577a90ebb3c447a31fd8a7306669293651b02a3b4cdbd2d36a6b4e9e07`; service success/exit0. The reviewed source commits only after those gates, so successful return demonstrates its local trusted commit path completed. Commit SHA is not present in the pasted receipt and must be taken from the retained export manifest before review.

Retain `/var/lib/rras-engineering/paid-canary-bd70070307cb45dd8ccc9890c888afef` and root review -05. This demonstrates one disposable model-backed native engineering task from dispatch through completion, verified stop, tests, local commit and evidence export. It does **not** demonstrate arbitrary-repository production operation, merge/deployment, database indexing or autonomous Jarvis submission. database_indexed=false; native_session_id=null, although a Codex rollout file reference was retained. API calls and spending remain unknown; do not claim a dollar ceiling was enforced. No authorization remains for another paid attempt.

### Ordered work after the successful canary

1. Human review of the retained hash-verified export, baseline-to-result calc.py patch, clean status and head commit; review portal usage separately. Preserve prior failed tasks rather than relabeling them successful. No fixture branch should be merged into an application repository.
2. Prepare a reviewed **manual admitted-repository task runner** from the successful path: remove hardcoded calc.py/test/task fixture assumptions; accept repository/task/validation inputs; keep native worktree/claim/lifecycle and exact per-run context. Keep commit ownership explicit rather than allowing arbitrary staging. Acceptance: model-free success, failed validation, unexpected changes, stale-run refusal and timeout/stop ambiguity on a disposable admitted repo; evidence retained for every outcome, no publication. Then one separately authorized small real task.
3. Install that reviewed manual entry point under the dedicated identity as an operator-invoked service, disabled by default; preserve native-10 and existing legacy units/timer. Acceptance: installed credential-free path, correct admission/profile/runtime, cgroup exit handling and rollback; deployment commands require a reviewed new release.
4. Add Jarvis submission using the same admitted task contract and review/evidence index. RRAS owns submitter identity, repo admission and traceability; Hermes continues to own Kanban/worktrees/workers. Acceptance: unauthorized repo/identity refused, concurrency respected, automated and manual entry points produce compatible evidence, no merge/deploy authority.
5. Add ledger indexing only after dedicated deployment endpoint/schema/grants are verified read-only; no admin role, migrations or networking changes inferred. GUI, interactive handoff, stronger independent containment and hard RRAS budget enforcement remain later upgrades. Portal spending policy remains current operator control.

Next source slice is item2, following human export review. It turns the demonstrated disposable canary into the smallest useful manual engineering workflow before adding automation or another independent orchestrator.

## Next slice prepared

See [manual admitted-repository runner review](rras-native-manual-runner-review.md) for the generalized source, six-case model-free evidence, bounded UID996 operator acceptance command and remaining real-task inputs. This does not authorize another paid task or install a production service.

Manual runner host acceptance subsequently passed all six model-free cases under UID996 in run `592ceb6681574b8cabf3411559831273`; see the linked manual-runner review. First real repository/task selection remains an operator input; no new paid run is authorized.
