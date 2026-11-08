# Private evidence custody

This implements the artifact intake in approved v0.4, without enabling collection
or upgrading a production store. The existing metadata upgrade remains an
explicit schema 3 → 4 operation. Byte custody is a separate reviewed schema
4 → 5 operation. The owner-only evidence CLI prints an exact migration plan and
requires its digest before applying it; no read, upload or service start migrates
the database implicitly.

## Storage and bounds

The service retains bytes below its existing private store in `evidence/chunks`.
Directories are owned by the service and mode 0700; files are mode 0600, named
only by their SHA-256, and must be regular files with one link. Symlinks, unsafe
permissions, altered lengths/digests and arbitrary paths/URLs are refused.

Each RPC upload carries one canonical base64 chunk of at most 65,536 bytes.
Reporting manifests already bound artifacts to 64 MiB and 1,024 chunks. The
initial implementation additionally bounds physical storage to 8 GiB and 131,072
files, scoped logical storage to 2 GiB, and custody receipts to 1,000,000. The
existing reporting stream separately retains its 10,000-record bound. Capacity
failure refuses new intake and requires the producer to preserve its private
pending export; it never deletes accepted evidence. Capacity/retention changes
must preserve the agreed no-automatic-deletion policy.

SQLite stores immutable upload receipts and a rebuildable scoped chunk index,
not the exported bytes. Identical bytes may share physical storage, but each scope
must have its own authorized upload/receipt. A caller cannot finalize a manifest
by guessing a digest retained for another scope. No cross-scope storage counts
or deduplication results are returned.

## Commit, replay and association

Bytes and their directory entry are synced before the upload receipt commits.
A stable principal/key binds the exact descriptor and content digest. Repeating
the same request returns its retained receipt; changed requests under that key
are refused. A crash before the database commit may leave an orphan immutable
file, which still counts against physical capacity and is verified before reuse.
A lost acknowledgment after commit does not produce another receipt on replay.

`artifact.record` is accepted only after every chunk is present in the submitting
scope and the service verifies chunk lengths, chunk digests and the complete
ordered-content digest. Revisions retain their source session/collector identity
and reference an exact prior manifest request. Empty artifacts use the exact
empty-content digest and no chunks. An unassociated artifact may retain null
project context; explicit association and correction are append-only and bind an
exact retained manifest. No repository-to-project inference occurs.

## Reads and historical boundaries

Chunk reads require the exact artifact revision and a verified scope-bound signed
snapshot. The manifest must exist within that snapshot's reporting boundary.
Earlier signed views cannot acquire a later artifact, version or association;
the immutable manifest already pins all relevant byte digests, so custody upload
receipts do not create an additional historical-view stream. Each returned chunk
is verified again before delivery. The dashboard reader verifies chunk digest and
length too. Historical metadata remains readable if bytes are unavailable, while
a byte read fails instead of returning substituted content.

Existing private-read/write scope grants authorize reads/uploads respectively.
The browser exposes reads only, behind its existing access boundary. The service
does not give Hermes a private-history mount or new grants. Curated summaries
continue to exclude full transcripts unless separately admitted.

## Installation and recovery

`evidence_entry.py` exposes `migration-plan`, `migrate`, `upload` and `read`.
Migration uses `--store` under the service owner; normal clients use the scoped
Unix API. Upload methods cannot select an owner, filesystem path or migration.
The release includes the custodian and CLI bootstrap in its explicit file list.

A backup must contain the SQLite database and the referenced private chunk tree
from a quiescent or consistently captured boundary. Restoring the database alone
does not restore evidence. Preserve later version-5 receipts and files rather
than rewriting old rows or rolling back to a runtime that cannot read version 5.
The actual production backup/restore and host acceptance remain separate rollout
work; source tests do not establish them.

The focused evidence/reporting/dashboard/package run passed 115 tests, including
old-record/schema/view preservation, exact replay, lost acknowledgment, orphan
reuse, corruption/link/permission refusal, scope denial and real Unix/HTTP reads.
No production migration or automatic collector was activated by those tests.
