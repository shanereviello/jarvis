# Protected historical review-document handoff

PR58 defines passive exact-document intake. This source adds a root custody reader,
explicit private transfer and a pinned isolated cross-UID rehearsal. No production
export, intake, service update or paid task is performed by source merge.

## Historical custody, separate from execution admission

`review_document_export.snapshot` requires root execution from protected code and
an explicit private-export flag. The selected original code release and exact
manifest hash are supplied by the trusted operator. Every bounded manifest member
is checked for protected custody and digest before that release's document module
is imported. The reader requires the captured control-code map to match that exact
version, verifies the original protected capture digest and document association,
regenerates the complete document package with the original renderer, and compares
the separate protected Markdown bytes. Private input files retain the existing
root-only regular600/single-link checks.

This is historical reading. It deliberately does not call the live execution
validator or open current profile/configuration/credential contents. A Git ref,
admission configuration or session setting may legitimately change after a review.
The stored captured core and original source version remain the reference. Missing
or changed original code/capture/document bytes refuse. This reader never creates,
consumes or upgrades an approval and cannot turn a historical record into a launch
grant. Existing live admission checks remain unchanged for execution.

The output is the existing private/imported/no-authority review-document packet.
It contains the exact document already selected for review, including private
metadata inside that document. It excludes approval records and tokens. It is not
safe for Git, public logs, shared narrative search or an unauthenticated browser.
Hashes alone do not authenticate an editable user-owned copy.

## Private transfer

`handoff` is a separate explicit root operation. Production defaults reuse the
existing protected `/var/lib/rras-history-exports` and
`/var/lib/rras-history-handoffs` parents with exact root700/root711 roles. A fresh
`document-<export-id>` directory retains a root-private packet and digest manifest.
The receiver directory is populated and fsynced as root700 with600 files before
file ownership and finally directory ownership transfer to the fixed operator
UID/GID1000. Root performs no writes inside that receiver after transfer. The
retained root original supports later comparison. Existing or partial identities
refuse; no adoption, overwrite, retry, history submission or action occurs.

The core permits explicit protected fixture parents for the rehearsal, but the
reader identity stays1000. No arbitrary worker recipient or service credential is
introduced. Production use still needs a separately reviewed pinned tool package,
selected source/review/digests and private-export decision; this source is not an
installed root daemon or new sudo permission.

## Fixed host rehearsal

Evidence scope is `/var/lib/rras-history-review-handoff-acceptance-20261027`.
Numeric service UID/GID61111 and unknown61113 must be unused; no accounts are
created. Operator1000 is the importer, with actual worker996 denials too. A new
root-owned hash-pinned release stages synthetic Git admission/configuration and
private review documents. No production configuration, database or repository is
mounted or used. No task worker, systemd unit or Docker operation is started.

The root seed captures and renders a synthetic review without creating an execution
authorization. It then changes its own synthetic live configuration and verifies
that the existing execution loader refuses. The historical reader must still
verify/export the immutable document. Root seed/export and all service/client
children use the existing native Python with pinned offline vendor bytes, private
network namespaces, no supplementary groups, no capabilities, no-new-privileges
and a credential-free environment. The root controller alone performs fixed
filesystem ownership transfer and tracks/stops its own history-service process.

The dedicated service uses the existing Unix API and per-UID socket ACLs. Tests
exercise exact packet handoff, source/database/policy/unknown-worker denial,
lost response after document commit, service restart/resume with exact Markdown
readback, another restart and the original receipt without duplicate document
records. The synthetic work is explicitly submitted by the fixture; the receiver
still never creates it implicitly. Root source file hashes must remain unchanged;
imported document storage grants no execution or human authority.

Success stops the fixture service and removes its socket, retains protected
evidence and reports zero API calls and no production mutations. Failure preserves
private diagnostics and stops only the tracked fixture process; the one-time scope
must not be rerun automatically. The stdlib bootstrap verifies and stages code
before importing payload modules. Its native interpreter matches the offline
validator dependencies; it does not use system Python for compiled dependencies.

Offline source tests establish custody consistency, historical revocation behavior,
transfer ordering, committed packaging, role boundaries and real disposable SQLite
recovery. Actual root ownership/cross-UID acceptance is pending until the pinned
operator-run sudo command returns its success result. A later real selected
work/document import and any production tool installation remain separate decisions.
