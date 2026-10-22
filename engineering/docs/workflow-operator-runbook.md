# Reusable managed workflow operator runbook

Use this sequence for an admitted repository and bounded task. Repository-specific
registration, allowed paths and validation are reviewed data, not generated launcher
code. Do not rerun dated acceptance/migration scripts for a new task.

The control/finish/validation/publication path is installed in
`/opt/rras-engineering/releases/workflow-b51bcece0851`. Automatic safe workspace
selection described below is a **closeout source correction awaiting installation**.
Until installed, pass an explicit fresh directory directly under the operator home
whose entire ancestor chain is root/operator-owned and not group/other writable.
Do not put operator publication custody beneath `Documents` if its ancestors are
mode0775. Never change broad directory permissions to make a task proceed.

## 1. Prepare and review

Prepare `registration.json` and a revisioned `work-item.json` using the shared
contracts. An administrator must first admit the repository through its own
protected `/etc/rras-engineering/workflow/REPOSITORY.json`; source preparation alone
cannot install a registration. Only SHA-1 repositories and admitted exact regular
file changes/recipes are supported by this path. Independent tree reconstruction
currently refuses baseline special entries, including submodules/symlinks; broader
repository support needs reviewed implementation rather than a new shell recipe.

Commands below use uppercase placeholders for reviewed paths/IDs, not literal
values. Run unprivileged preparation first:

```sh
rras-workflow prepare --registration REGISTRATION --work-item WORK_ITEM \
  --hermes-project PROJECT --state PROPOSALS
```

Record the candidate ID, then capture/review as administrator:

```sh
sudo rras-workflow capture --config CONFIG --proposals PROPOSALS \
  --candidate-id CANDIDATE_SHA --state CONTROL --review-branch codex/TASK_SLUG
sudo rras-workflow review --config CONFIG --state CONTROL --review-id REVIEW_SHA
```

Review the objective, scope, baseline, recipe, limits and model/spending implications.
Capture does not authorize execution. Configuration/baseline changes require a new
review; do not edit protected records.

## 2. Explicit paid execution decision

Only after the human approves this exact run:

```sh
sudo rras-workflow approve --config CONFIG --state CONTROL \
  --review-id REVIEW_SHA --approve-one-execution
sudo rras-workflow launch --config CONFIG --state CONTROL \
  --authorization-id AUTH_ID --jobs /opt/rras-coding-jobs \
  --workers /var/lib/rras-coding-tasks \
  --credential /etc/rras-engineering/credentials/openai_api_key
sudo rras-workflow evidence --state CONTROL --authorization-id AUTH_ID
```

Never read/copy the key. A timeout is not a dollar cap. The authorization is one-use;
uncertainty/failure requires inspection, not deletion of fences, automatic retry or
a new approval inferred from a general instruction to continue.

## 3. Stopped-worker evidence

Require verified stop, then use fresh root-private destinations under CONTROL:

```sh
sudo rras-workflow finish-capture --state CONTROL --authorization-id AUTH_ID \
  --destination FINISH
sudo rras-workflow finish-record --custody FINISH
sudo rras-workflow native-observe --finish-custody FINISH --destination OBSERVATION
sudo rras-workflow native-record --finish-custody FINISH --observation OBSERVATION
```

Finish claims are imported. A read-only native database observation establishes
stored agreement, not authenticated worker behavior or deliverable correctness.
Preserve partial custody on failure and inspect it without relaunching the worker.

## 4. Local review preparation and independent validation

Select the actual protected installed release as RELEASE. Source module invocations
below use the protected release, not the writable development checkout. A protected
publication policy must already match the admitted repository/assigned branch.
Choose a fresh root-private REVIEW_CHECKOUT, a fresh root-owned PACKAGE under a
readable protected parent, and a fresh root-private VALIDATION stage.

```sh
sudo rras-workflow publication-prepare --finish-custody FINISH --policy POLICY \
  --destination REVIEW_CHECKOUT --package PACKAGE --operator OPERATOR_ACCOUNT
sudo rras-workflow validation-stage --finish-custody FINISH --package PACKAGE --destination VALIDATION
sudo rras-workflow validation-stage-verify --finish-custody FINISH --package PACKAGE --destination VALIDATION
sudo rras-workflow validation-execute --finish-custody FINISH --package PACKAGE --destination VALIDATION
sudo rras-workflow validation-record --finish-custody FINISH --package PACKAGE --destination VALIDATION
sudo rras-workflow validation-release --finish-custody FINISH --package PACKAGE --destination VALIDATION
```

Validation uses the fixed isolated worker identity/slot without model credentials.
Its proof binds the exact review commit; new files are included by intent-to-add
against baseline HEAD. A successful mechanical check does not accept the deliverable.
No automatic validation execution retry is supported.

## 5. Operator diff review, branch and draft PR

After installing the closeout correction, omit workspace to select a deterministic
private directory under the operator's account-database home:

```sh
/opt/rras-engineering/releases/native-10/venv/bin/python \
  RELEASE/engineering/tools/rras_native/publication_handoff.py \
  --action import --package PACKAGE
```

The output's `checkout` identifies the local review repository. Inspect its exact
baseline-to-review diff and compare every requested deliverable. Obtain explicit
human acceptance; preserve it as a human decision rather than inferring it from a
validation exit. The operator workspace is the checkout's parent. Explicit custom
`--workspace WORKSPACE` remains supported only with safe ancestors.

After acceptance, standing own-branch publication allows:

```sh
/opt/rras-engineering/releases/native-10/venv/bin/python \
  RELEASE/engineering/tools/rras_native/publication_handoff.py \
  --action publish --package PACKAGE
```

The connected Codex operator frontend evaluates only the reviewed protected
`RELEASE/entrypoints/draft-pr-frontend.js` function expression with the current trusted
`tools`, `release` and `packagePath`. Omit `workspace` for host-selected defaults, or
supply the same explicit safe workspace used for import/publish. This is frontend
integration, not a standalone Node/server command. The frontend performs live
branch/PR preflight, one-use arm/create/receipt handling and PR attachment. There is
no worker GitHub credential, new token or daemon. If an intent/fence/outcome exists,
inspect it; never rerun creation blindly after a lost response.

## 6. Record publication and explicit decisions

```sh
sudo rras-workflow publication-capture --finish-custody FINISH --package PACKAGE \
  --workspace WORKSPACE --destination PUBLICATION_CUSTODY \
  --pr-receipt WORKSPACE/draft-pr-receipt.json
sudo rras-workflow publication-record --finish-custody FINISH --custody PUBLICATION_CUSTODY
```

Merge and deployment need separate human decisions. Capture each exact decision
and actual GitHub result before claiming either in history. The supported passive
`rras-workflow-journal append --store STORE --records RECORDS --artifact SHA256=FILE`
interface accepts explicit schema-valid decision/merge records. It does not fetch
GitHub, authenticate a chat message or authorize the described action. Decision
subjects are `deliverable_acceptance`, `merge` and `deployment`; merge completion is
`change.merged`. Preserve provenance, actual occurrence time when known, evidence
bytes and the existing stream's next sequence/previous event digest. A retrospective
human import must disclose unavailable original timestamps. Unknown source facts
stay unknown. Do not fabricate receipts or rewrite earlier events. The recording
CLI remains generic; a guided human-decision client is not implemented.

## 7. Refresh and read history

After durable writes, explicitly publish a new complete snapshot generation:

```sh
sudo rras-workflow-publish --store /var/lib/rras-workflow/journal \
  --directory /var/lib/rras-workflow/history --reader-gid 1000
sudo rras-workflow-journal status --store /var/lib/rras-workflow/journal --repository-id REPOSITORY
sudo rras-workflow-journal summary --store /var/lib/rras-workflow/journal --work-id WORK_ID
```

The last two commands are private operator queries: do not publish their raw output.
Jarvis reads only `/opt/rras-workflow-history` through its projection-only MCP reader;
operators can inspect the host `/var/lib/rras-workflow/history/index.json` and its
named pages without sudo. Events retain outcomes and provenance. Snapshots omit
private objectives, text, raw artifacts and arbitrary paths; they are not the
engineering narrative or release-notes product. `not_inferred` is not a failed run:
merge/deployment/verification remain separate facts. Pending outbox entries do not
mean a ledger received them. Off-host backup/ledger indexing remains deferred.
