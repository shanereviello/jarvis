# Curated read-only dispatch and local Unix transport

`curated_read_access.py` and `curated_read_unix.py` provide a separate curated
reader adapter for the private local publication catalog. They do not modify the
installed engineering-history service, its private permissions or its existing
Unix endpoint. No production listener, service/account, ACL, catalog publication,
Jarvis mount or MCP tool is installed by this source slice.

## Read policy and routes

Trusted policy `engineering-curated-read-access.v1` contains exact principal UIDs
and repository lists. It has no private-read/write/admin fields. Root, UID996/997,
duplicate identities and grants outside the catalog repository allowlist refuse.
The caller UID comes from the kernel peer socket, never a request actor field.
Policy is a server-start snapshot; changing the file does not silently alter a
running server. A future production entrypoint must load/protect policy and revoke
connection ACLs when restarting, as in the separately reviewed service pattern.

Only two exact message shapes exist:

- `search`: repository, query, current/explicit generation, offset and bounded limit.
- `read`: repository, exact curated entry ID and exact current generation digest.

Authorization precedes catalog search or entry lookup. Search has no source-store
fallback, private snippets or arbitrary file/URL fetch. Read finds only the current
curated entry; a withdrawn old generation refuses. Writer/publication/private
history/document/action routes are absent. Repository membership in JSON grants
nothing. Local publication receipts do not authenticate a human, and all returned
claims retain the source/provenance/authority limits of the curated foundation.

## Transport reuse and limits

The curated server subclasses the existing passive Unix transport with its own
strict dispatcher; the existing private-history dispatcher/default server are
unchanged. Kernel peer checks, protected endpoint ancestors, one-frame protocol,
request/response bounds, absolute deadlines, uniform refusal and inode-checked
socket cleanup are reused. Clients verify socket ownership and connected service
UID before sending data. The read endpoint does not receive source history rows or
publish/withdraw requests.

The constructor permits an optional trusted `on_bound` callback for later exact
per-UID endpoint ACL preparation. It does not execute an ACL command itself or
choose real service/reader identities. A production daemon entrypoint, hardened
unit, policy custody, endpoint ACL revocation, Jarvis transport and installation
remain separate source/host/deployment work. Do not mount the private catalog or
engineering DB into Hermes to avoid those boundaries.

## Evidence and next gate

Disposable same-UID Linux sockets establish real local framing/peer transport,
search/read, route refusal, endpoint cleanup, wrong-service identity refusal and
withdrawal surviving restart. Dispatcher fixtures establish unknown/root/worker/
repository policy denials. These do not establish distinct-UID permissions or a
production installation. The filesystem sandbox maps root ancestors to an
untrusted UID, so actual socket tests run as the ordinary operator outside that
mapping; no sudo or production resources are used.

Next prepare an isolated cross-UID fixture with a dedicated temporary numeric
service role and separate allowed/denied readers, private networks, no provider
credentials and exact endpoint ACLs. It must prove direct catalog/private-history
access denial, allowed repository-only retrieval, forbidden routes, withdrawal,
restart and revocation. Concrete production identity/entrypoint choices and actual
content sharing require separate review. Browser authentication decision D2 remains
open; this local read protocol does not resolve it or authorize a listener.
