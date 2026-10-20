# Named-operator draft-PR connector bridge

This source slice joins the protected publication handoff to the GitHub connector
already available to the human's Codex frontend. It does not provision a server token,
install/authenticate `gh`, expose GitHub tools to UID996 or add a publication MCP tool.
The live immutable workflow release is unchanged. Source merge is not installation
or permission to run a managed task.

## Components and sequence

`draft_pr_connector.py` runs as the named operator against protected installed code,
a root-reviewed handoff package and that operator's private publication workspace.
The existing source bundle, clean exact review commit/branch, standing policy and
published transport receipt must still verify. The package must admit GitHub draft
PR publication for that task-assigned branch.

1. `prepare --package PACKAGE --workspace WORKSPACE` saves an idempotent private
   intent binding handoff, published receipt and exact create arguments. Title/body
   use bounded task/commit/export metadata, not objectives, logs, credentials or
   private paths. Its output includes exact branch/PR-list GET requests and draft
   creation arguments for the authenticated connector. A prior armed/outcome/PR
   receipt refuses rather than creating again.
2. The frontend fetches the exact branch and a head-filtered all-state PR collection
   (`per_page=1`). Any existing PR or unexpected response refuses. A closed prior PR
   is not silently adopted or replaced. This read does not eliminate GitHub races.
3. `arm --package PACKAGE --workspace WORKSPACE --data JSON` rechecks the protected
   package/local commit and exact remote branch SHA from the connector result, then
   exclusively creates `draft-pr-armed.json` before any creation call. An existing
   fence always refuses, including after a lost arm reply. Creating the fence does
   not prove a GitHub call happened; it preserves uncertainty when that is unknown.
4. The frontend calls the existing `github_create_pull_request` connector with only
   the exact returned arguments: repository, assigned head, reviewed base, fixed
   metadata, draft true and maintainer-can-modify false. No merge/deploy request is
   supported. The create endpoint has no expected-head-SHA compare-and-swap; the
   response must therefore be checked again for head movement.
5. `complete ... --data JSON` normalizes the connector or REST response and reuses
   the strict publication PR validator. Matching open/draft/unmerged repo/head/base/
   commit/URL/number produce `draft-pr-receipt.json` and a private outcome. Unexpected
   metadata records unknown and, when safe, a candidate URL/number for read-only
   inspection; it never closes/deletes a PR or retries creation.
6. A missing/failed connector response invokes `unknown ...`, retaining the fence
   and recording unknown without raw error text. Host failure after creation leaves
   existing intent/fence/receipt evidence for inspection. A successful receipt can
   feed the existing root publication capture and journal commands. Those final
   records remain imported named-operator reports, not independent GitHub attestation.

There is no automatic create retry or adoption/reconciliation write interface in
this slice. Inspect unknown outcomes through read-only GitHub queries and retained
files. Do not delete fences or rerun creation to repair journaling/attachments.

## Operator frontend binding

`draft_pr_frontend.js` is an async function expression accepting three explicit
trusted adapters:

- `cli(action, data)` invokes the protected Python bridge as the named operator with
  fixed package/workspace arguments and returns parsed JSON. It must preserve argv
  literally (proper shell quoting or structured subprocess args), wait for completion
  and throw on failure. It must not replace a failed host command with a new creation.
- `github(name, args)` dispatches only `fetch` and `create_pull_request` to the current
  operator's already connected GitHub tools. The adapter recognizes the connector's
  fetch envelope (`structuredContent.content` containing JSON) and normalized create
  snapshot. It strips unrelated response fields before host receipt processing.
- `attach(url)` calls the Codex task's pull-request attachment tool for every created
  PR with a valid GitHub URL, even if the returned head raced and requires inspection.
  Attachment failure is surfaced as pending, while receipt recording continues.

This function executes in the operator frontend (such as the current Codex tool
context), not in the coding worker or a new server daemon. Callbacks are trusted
operator integration code, not model-worker arguments or proof of authentication.
Only use reviewed/protected frontend code; never evaluate worker-provided JavaScript.
An unattended standalone host client is not supplied, and GUI/autopilot remains
separate. The current source interface must be included in a reviewed installation
and have an actual frontend binding before production use.

## Authority, validation and remaining work

A named operator can fabricate input reports; capture never upgrades them to observed
execution or human acceptance. Client and filesystem checks enforce consistency and
one-use behavior within the trusted operator contract, not a cryptographic proof of
GitHub origin. Existing merge/deploy decisions and separately scoped paid execution
remain unchanged.

Python tests use real disposable local Git handoffs/workspaces with fake GitHub
metadata. Frontend cases run with fake CLI/connector/attachment adapters in the same
JavaScript runtime used by the Codex frontend. Cases cover exact arguments, preflight
refusal, lost responses, head races, malformed metadata, attachment failure, host
failure, no duplicate creation and normalized receipt/journal integration. A read-only
query of the existing GitHub branch API confirmed its actual connector envelope;
no managed draft PR was created as acceptance. Source PRs are ordinary development
publication, not proof of the managed end-to-end path.

Next: reviewed dependency packaging/upgrade and model-free root/UID acceptance,
independent post-validation where required, and a separately scoped real-task/remote
acceptance. Existing first-install helpers/module lists are not upgrade procedures.

For new managed handoffs, the shared package reader also requires a protected
independent-validation proof matching the exact handoff/commit/export before
preparation or creation can proceed. The generated PR body identifies that check
separately from the imported runner report. This gate does not authenticate task
correctness, human acceptance, merge or deployment. See
[independent validation](post-validation.md); production binding/installation and
host/remote acceptance remain separate.
