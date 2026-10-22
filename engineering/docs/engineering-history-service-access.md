# Engineering-history service access boundary

This source slice adds `tools/rras_history/access.py`, an internal dispatcher for
the dedicated unprivileged history service. It is not a running service. No socket,
account, production store, policy file, root exporter or browser interface is
installed. The interactive client still uses its existing caller-owned local
transport and v1 receipts.

## Authentication and grants

The future Unix adapter must obtain the caller UID from kernel peer credentials
and pass it separately to `Access.dispatch(peer_uid, message)`. It must never copy
a UID from request JSON. This library deliberately does not claim to authenticate
a process itself. Calling it directly in a test supplies a simulated peer.

A trusted in-memory policy has this exact shape (illustrative UIDs only):

```json
{
  "contract": "engineering-history-access.v1",
  "principals": [
    {"uid": 2001, "private_read": ["example"], "write": ["example"]},
    {"uid": 2002, "private_read": ["example"], "write": []}
  ]
}
```

Grants name exact registered repository labels, never wildcards. Writing requires
an explicit private-read grant because submission returns private heads/document
receipts. Root and worker/control UIDs 996/997 are refused. Unknown callers have no
access. These grants permit private narrative access; do not assign them to Jarvis
as a substitute for the later curated-publication mechanism. Sharing an OS account
shares that principal: the UID does not prove a human personally approved anything.

The policy is copied at construction. A future daemon must load protected policy
and replace/restart the dispatcher for revocation. Every call checks current grants,
including duplicate writes; an old receipt key cannot bypass revoked permissions.
No credentials or user-selected policy arrive through service messages.

## Fixed passive messages

- `submit`: exactly `method` and `request`, using the existing strict engineering
  envelope. Repository grants cover both the proposed and existing work repository.
  Revisions cannot move work into another repository. All source claims retain
  their declared provenance and grant no execution or human decision authority.
- `history`: exactly `method`, `repository_id`, `offset`, `limit`. Authorize first,
  filter by repository, then paginate up to 100 records. No unscoped history route.
- `document`: exactly `method`, `document_id`, `version` (positive integer or null
  for latest). Return stored immutable Markdown and manifest only for a permitted
  work repository. Missing and unauthorized documents both report unavailable.

No outbox, action, shell, publish, protected-journal or credential route exists.
References remain untrusted reported text; this dispatcher never fetches them.
Private read permission covers all work in the named repository, not per-session
ownership. Returned receipts retain the store-global sequence and actual writer
UID; these are association metadata, not a promise to conceal aggregate activity
from an authorized private reader. Pagination totals count only the requested
repository. Later remote/curated views need their own sanitized metadata contract.

## Service receipts and compatibility

Local direct writes retain `engineering-history-receipt.v1` and
`transport: local_caller_store`. Service writes use
`engineering-history-receipt.v2`, `transport: authenticated_local_service`,
`writer_uid` for the service/store owner and `peer_uid` for the transport caller.
All other association fields remain: immutable receipt ID, sequence, request hash,
work/revision, recording time, reported provenance, private visibility,
`authority_granted: false` and optional document manifest.

The SQLite submission principal uses a separate negative internal namespace for
service peer UIDs; positive local caller keys remain unchanged. Thus service and
legacy local submissions cannot accidentally reuse each other's idempotency keys,
and two peers have distinct replay domains. Existing local databases/receipts need
no schema migration. This does not make the database tamper-proof against its owner.
The service owner is the trusted writer. Only the service should be able to open
its eventual store directory; clients must not have direct database access.

The current interactive client intentionally refuses service receipts: the next
transport slice must configure and verify the expected service identity and peer,
update receipt checks explicitly, and retain pending data on failures. Do not point
its local-store configuration at a shared service database.

## Validation and remaining work

Tests exercise real disposable SQLite plus supplied test UIDs: scoped writes/reads,
private documents, filtered pagination, caller-specific duplicate receipts across
reopen, local/service replay separation, revoked grants, conflicting keys and
identity claims without authority. These are source policy tests, not evidence of
actual cross-UID isolation or kernel authentication.

Next: bounded Unix framing, SO_PEERCRED verification in both directions, safe socket
lifecycle/timeouts, protected policy loading and explicit interactive transport
configuration. Then package an isolated cross-UID host acceptance for human-run sudo.
Deployment of the dedicated account/store/unit and any browser listener still need
separate approval. Root operational export and curated narrative publication remain
later work under the [accepted design](engineering-history-phase1/README.md).
