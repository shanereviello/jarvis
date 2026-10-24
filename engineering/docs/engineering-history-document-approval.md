# Protected review-document custody and versioned approval

This source slice connects the passive standard-document constructor to the
existing root operator control. It does not install code, change production
approvals, import history or start a paid run. Host isolation acceptance and a
separate installation decision are required before production use.

## Protected preparation and review

The new operator subcommands are `document-prepare`, `document-review` and
`document-approve`. All require existing root-protected operator state and a live
configuration matching the captured admission. Preparation takes the capture digest,
an explicit engineering work request, curated narrative and document ID. Selected
proposal inputs must be canonical regular single-link600 JSON files, at most 128 KiB;
symlinks, devices/FIFOs, duplicate keys and oversized inputs refuse. The
capture itself is read from protected state, never from caller-supplied JSON.
Engineering work identity must equal the admitted operational work identity;
repository, baseline and ordered scope checks come from the standard constructor.
Engineering and operational revision numbers are still independently bound.

Preparation rechecks live registration, code/config hashes and Git baseline through
the existing validator. It verifies protected document dependency paths. Under a
shared nonblocking approval lock it writes two fixed private600 files beneath the
existing root-private control directory:

- `<review-id>.review.md`: the exact standalone standard Markdown document.
- `<review-id>.review-document.json`: curated input, passive document request,
  manifest, companion binding and selected configuration path.

The files are immutable exclusive/idempotent writes with fsync. An existing
attachment with changed bytes refuses. A failed partial preparation preserves its
files; it does not repair them or authorize execution. Changed content needs a
fresh protected capture/revision rather than replacement of an attached document.
No raw configuration contents, credentials, worker output or transcript is read.
The private document includes captured metadata and must stay out of Git/public
logs. Source/render/template/contract dependencies are included in control hashes
and in the committed-source release builder's explicit file list.

`document-review` returns exact Markdown, manifest, private Markdown filename and
binding/Markdown digests. An external viewer may present those bytes, but editing
an exported copy does not change the protected file. Reading the view grants no
execution authority. Root file loading requires protected ancestors, single-link
regular600 custody and existing transport-independent root operator checks.

## Explicit v2 approval and launch

After human review, the operator uses `document-approve` with the exact capture ID,
companion binding SHA256, Markdown SHA256 and `--approve-one-execution`. The adapter
reloads protected custody, regenerates the complete package, compares the separate
Markdown bytes, rechecks live admission/configuration and requires both selected
digests. It writes a new `schema_version=2` authorization carrying document binding,
manifest and Markdown hashes, plus the existing authorization/review/root-UID and
no-publication fields. Root operator invocation represents the existing trusted
human decision boundary; ordinary history clients do not gain this route.

The existing `launch` path recognizes both protocols. V2 verification repeats
before launch side effects/journal preparation and again immediately before the
existing exclusive consumption fence. A missing/changed document, altered package,
wrong capture, changed configuration or unknown approval protocol refuses without
consuming the grant or invoking the service. Successful consumption retains the
fixed-slot/one-use behavior. An ambiguous failure after consumption cannot retry
with that grant. Mechanical verification is not task success or human acceptance.

Once a document attachment exists, new legacy `approve` calls for that capture
refuse; the same lock serializes attachment and approval creation. A v1 grant
created before attachment retains its original meaning and existing launch checks.
No old grant is silently upgraded to document-bound approval. New v2 grants cannot
be treated as v1 while retaining document-specific fields. Root administrators
remain trusted custodians; this is not protection against a malicious root user.

Examples of the additional arguments, for a reviewed installed operator wrapper:

```text
document-prepare --state CONTROL --review-id CAPTURE --config CONFIG --work-request WORK_JSON --narrative NARRATIVE_JSON --document-id DOCUMENT_ID
document-review --state CONTROL --review-id CAPTURE --config CONFIG
document-approve --state CONTROL --review-id CAPTURE --config CONFIG --binding-sha256 BINDING_SHA --markdown-sha256 MARKDOWN_SHA --approve-one-execution
```

These describe a future installed interface, not permission to run source code
under sudo. Existing protected capture and launch arguments remain unchanged.
The installed wrapper will require a configured operational journal for the new
commands as it already does for managed capture/approval/launch. Approval journaling
uses the existing receipt/reconciliation path; a journal error can leave an
approval file present. Preserve it and inspect/reconcile, rather than creating
another approval or retrying a coding run to repair the log.

## Acceptance and remaining work

Disposable tests use real Git admission/SQLite-capable source paths with mocked
root custody and a fake service manager. They cover exact standalone bytes,
immutable attachment, explicit hash/flag selection, v2 launch/replay, stale config,
missing/tampered package/Markdown, wrong work/capture, protocol downgrade refusal,
legacy continuity and concurrent approval lock exclusion. The generated production
candidate includes document dependencies and its actual isolated operator entrypoint
exposes the new commands. These tests establish source semantics, not actual root
ownership, cross-UID denial or host launch acceptance.

Next: a pinned isolated root/distinct-UID fixture with harmless fake execution;
then reviewed inactive packaging/upgrade and separate installation approval.
Explicit transfer of the stored passive document request into engineering history
still needs the reviewed handoff/intake path. Nothing here automatically publishes
a narrative to Jarvis, imports records, exports later lifecycle events, installs a
scheduler or changes browser/network decisions. No real provider credential or paid
model call is needed for the next host fixture.
