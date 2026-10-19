# Shared workflow record contracts, version1

Schema: `engineering/contracts/workflow-v1.schema.json` (JSON Schema2020-12).
`workflow_records.py` validates data and a complete history without Git, network,
service, credential, ledger or worker calls. These contracts are not connected to
existing admission/approval/launch/publication entrypoints yet. Validation requires
`engineering/requirements-contracts.txt`; production packaging is future work.

## Records and identities

| Record | Identity and immutable binding | Meaning |
|---|---|---|
| Repository registration | Stable `repository_id`, `reg_` ID, positive revision and previous snapshot SHA256 | Canonical path, optional credential-free SSH/HTTPS remote, Git object format, baseline refs, literal path-policy roots, named validation recipes and review-branch policy. No repository is registered on the host by creating this data. |
| Work item | `wrk_` ID, revision/previous snapshot SHA256, repository registration SHA256 | Objective, requested paths, optional validation/baseline, actor, provenance and mode. A changed objective/scope/configuration produces another immutable revision; attempts retain their original snapshot. |
| Attempt | `att_` ID, per-work attempt number, exact work/registration SHA256 | One execution/import attempt and optional authorization/delegation references. No implicit retry. Native task/run/session identities can arrive through later event references. Results are events, not rewrites of the attempt. |
| Event | `evt_` ID, per-work sequence, previous event SHA256, work snapshot and optional attempt ID | Append-only observation/claim. Sequence spans attempts and work revisions. Correct mistakes using a new event referencing an earlier event in the same work item, never erase a failure. |

Entity IDs use UUID-style32lowercase-hex suffixes. Repository/actor/recipe labels
use bounded identifiers. UTC timestamps include `Z`; `occurred_at` is source time,
`recorded_at` is capture time. Do not fabricate missing history: unknown baseline,
recipe or authorization references can be null. Before managed launch, the existing
trusted capture must still establish exact admitted paths, recipe and baseline.

Record hashing is SHA256 of sorted-key, compact, UTF-8 JSON plus newline with NaN
refused. It is the Python protocol defined by `encoded`, not a JCS/cross-language
canonicalization claim. New language adapters must reproduce those exact bytes or
introduce a reviewed version. SHA1/SHA256 Git object IDs are separate from record
SHA256; registration declares the Git format. Existing launcher still accepts its
current SHA1 contract; declaring SHA256 here does not add launcher support.

Repository path roots are literal normalized relative paths (`.` may mean the
repository root); no shell/glob evaluation occurs. `.git` must be denied. Registered
recipe argv begins with an absolute executable and identifies the low-privilege
engineering worker. Actual Git resolution, symlink/ownership checks, path admission,
protected instruction/configuration rules and policy freshness belong to trusted
adapters in the next slice. Do not replace those checks with schema validation.
Repository registration is an immutable snapshot; enabling/disabling or changing
policy requires a new revision. Old history continues to reference old snapshots.

## Modes, provenance and visibility

`interactive`, `approval_driven` and `delegated` describe how work originated.
Delegated records do not enable autopilot or grant execution permission. Attempts
may reference an existing root approval or a future delegation record; this schema
never consumes or validates either as authority. Existing single-slot, one-use,
verified-stop, human merge/deploy and spending policies remain unchanged.

Actors identify the subject/caller reported for an action; provenance separately
records who captured it and its source: `observed`, `imported` or `human_reported`.
A valid `observed` field is still only a claim until the capture adapter authenticates
its producer and checks its supporting artifact. Imported/human-reported merges or
deployments remain claims pending verification; they must not become verified
release notes through a schema check. Corrections remain visible in the journal.

Artifacts carry opaque IDs, SHA256, media type, purpose and intended visibility,
not embedded logs, credentials, filesystem locations or automatic download URLs.
An artifact ID keeps the same digest/metadata across history; reclassification uses
a new explicit reference rather than silently changing an old visibility label.
References carry namespaced opaque external identities; no reference is fetched by
validation. An artifact's `operator_and_jarvis` label is an audience request, not an
access grant. Storage/query layers must authenticate readers, resolve refs within
permitted roots and filter content; a user-authored label cannot publish private
material. Free text can still contain secrets: schema validation is not a secret
scanner. Capture/import adapters must redact and exclude sensitive payloads.

## Event semantics and future projections

Decision events include a structured subject (scope change, deliverable acceptance,
merge, deployment or other); their summary records the rationale. These recorded
decisions still do not grant runtime authority.

Distinct events represent preparation, decision/review/approval records, attempt
start/interruption/finish, validation, artifacts, branch publication, draft PR,
merge, deployment, field verification, cancellation and recovery. Native done is
not independent validation or human acceptance; publishing a branch is not merge,
merge is not deploy, and deploy is not field verification. Event outcomes preserve
pending/failed/uncertain/rejected/cancelled observations as well as success.

The future work-journal view includes all attempts and claims. Release-note views
must use separately verified merge/deploy/verification events, immutable references
and corrections; choose/report which release threshold is used. They must not infer
release from `attempt.finished` or `branch.published`. No projector/release-note
generator is implemented in this slice. Missing outcomes stay unknown, not success.

## Storage and consistency boundary

`validate_history` checks a complete set of snapshots/attempts and per-work event
chains. It rejects duplicate identities/revisions/numbers, cross-repository or
wrong-revision links, missing parents, sequence gaps and invalid corrections.
Filtered history queries must not be passed as complete histories. Event order is
logical sequence, not wall-clock timestamps; clocks can differ and imports arrive
late. A complete suffix can be deleted without a locally detectable broken link:
head custody/anchors and completeness checks are storage responsibilities.

Append-only is a writer requirement, not implemented durable storage. Next slice
must enforce exclusive append/head comparison, crash-safe persistence, immutable
revision IDs, bounded duplicate-key-rejecting input, idempotent import/index replay
and artifact custody. Retries of index delivery are not retries of coding execution.
No hash chain authenticates its writer or prevents rewriting an entire unanchored
history. No journal, outbox, ledger migration or live state file is created here.

## Mapping existing formats

Existing `task_id`, proposal/submission digest, root review digest, one-use
`authorization_id`, launch run ID, Hermes task/run, export digest, review commit,
publication receipt and PR identity remain authoritative in their current systems.
Link them through namespaced references/artifacts instead of renaming or rewriting
existing records. New work/attempt IDs group their evidence across modes. Existing
root approval is still separate from Hermes-writable proposals and worker evidence.

Examples are synthetic passive data, not repository enrollment, task approvals or
commands to run. Tests create no live task or service. After source review, later
adapter work must demonstrate two repository registrations using the same tools.
