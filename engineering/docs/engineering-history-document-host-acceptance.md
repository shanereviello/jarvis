# Isolated protected-document host acceptance

PR56 adds the protected document/v2 approval source. This fixture extends the
existing model-free workflow host probe with an opt-in document path; ordinary
probe behavior remains the default. No production rollout is performed.

## Fixed scope and custody

The fixture uses fresh `/var/lib/rras-document-approval-acceptance-20261025` and
private `/var/lib/rras-document-approval-acceptance-diagnostics-20261025` evidence
roots. The pinned read-only code release is
`/opt/rras-engineering/releases/document-approval-acceptance-<manifest-prefix>`.
Existing paths refuse; evidence is never adopted, removed or retried automatically.

The unprivileged builder reads committed Git bytes for an explicit fixed dependency
set, including the document schema/template/renderer. The sole runner substitution
is the exact literal `FAKE_WORKER` from the committed approved-launch fixture.
Synthetic profile/config and an example registration are bundled; an offline vendor
copy provides validators. It does not include real proposals/configs/credentials.
Manifest scope and exact fake-runner bytes are checked independently before staging.
The generated stdlib sudo helper verifies every bounded regular-file payload digest
before copying it into root-owned directories and importing any payload code.
Candidate symlinks, hardlinks, FIFOs/devices, unsafe names and altered bytes refuse.

## Actual isolated exercise

The trusted root probe requires the production worker slot and UID996 to be idle;
it does not stop or adopt a production unit. It creates a synthetic Git repository,
registration, work item, journal and protected control files. It selects a distinct
`rras-workflow-acceptance-<fixture-root-hash>.service` transient unit. The existing
launcher checks account identity, protected custody, code/config hashes, fixed-slot
exclusion and exclusive consumption; actual systemd runs the exact fake worker as
UID996 in a private network namespace with a delivered synthetic sentinel credential.
The worker contains no model call and does not import the coding engine. Only the
fixed existing native interpreter is reused; no provider key is opened.

Document-specific cases include exact standard Markdown view; explicit v2 hash/flag
selection; refusal of new legacy approval after attachment; changed/missing Markdown,
changed companion and wrong hash/protocol/capture refusal without consumption or
job staging; nonblocking approval-lock exclusion; actual v2 launch and replay refusal;
and a pre-attachment v1 grant still launching under its original semantics.
Deliberate changes affect only synthetic fixture copies. Originals are saved in
private evidence, and restoration happens only after the expected refusal succeeds.
Unexpected failures preserve the failed test state.

The root probe verifies actual root-owned single-link600 document custody. Separate
processes under UID996 and UID1000, with cleared groups/capabilities and a private
network namespace, must fail both file reads and writes and must fail the root
operator boundary. Existing journal/approval privacy, read-only projection,
configuration revocation, pending outbox retention and no inferred task success
checks run too. No accounts, ACLs, history sockets or permanent services are created.

## Result and failure limits

Success retains fixture evidence and the protected code release, verifies the
transient slot is gone, and reports no production service/journal/history mutation
and zero API calls. The fake worker never establishes a real coding task's success.
A subsequent source merge or production installation remains a separate decision.

The root bootstrap saves stdout/stderr privately, with a 480-second outer deadline.
The fixture launcher's existing 400-second service runtime limit still applies. On
failure or timeout, retain diagnostics and inspect the exact fixture unit; do not
repeat a partially consumed authorization or automatically stop a production unit.
A timeout does not prove that the fixture unit stopped. There is no production
rollback or cleanup in this harness. Operator-selected inactive installation and
actual history intake of the stored document request remain later steps.

Offline tests exercise committed packaging, exact fake-runner substitution,
tampering/path/nonregular input refusal, fixed bootstrap paths, existing-fixture
refusal and document case logic using real Git with fake root/service adapters.
These results do not establish real ownership or systemd boundaries. Actual sudo
acceptance is pending until the pinned operator command returns its success record.
