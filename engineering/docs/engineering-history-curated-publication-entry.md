# Curated publication request entry

The curated read endpoint and MCP client expose only search and read. Publication
uses a separate, non-listening entry, `curated_publication_entry.py`, intended for
a root-selected invocation inside the approved catalog-only write sandbox.
This source entry does not install or construct that sandbox, initialize a catalog,
change a reader grant, or publish any real content.

The production CLI requires service account UID 995, scrubs the environment and
uses the fixed `/var/lib/rras-curated-history/catalog` path. It reads at most
2 MiB plus one overflow-detection byte from standard input. The caller supplies
`--reviewed-request-sha256`, which binds the entire exact input byte string before
decoding. Whitespace changes therefore require a new packet digest.

Each packet has contract `engineering-curated-publication-request.v1`, an explicit
boolean `approved: true`, `operation`, bounded `client_key`, and exact
`expected_head` (null for an empty catalog). A publish packet additionally has
`preview` and `reviewed_preview_sha256`; a withdrawal packet instead has exact
`entry_ids`. Extra fields and other operations are refused. The existing catalog
validates the preview, repository scope, expected generation and replay key before
creating a generation. Replaying a prior publication after withdrawal returns its
original receipt without restoring the withdrawn content.

A packet flag and digest record selected intent; they do not authenticate a human.
Receipts retain `human_authenticated: false` and `authority_granted: false`.
The protected root launcher and operator decision must supply the authorization
boundary. Do not grant this command or its catalog write access to Hermes or the
reader account. UID 995 alone is insufficient isolation from the private history
service: deployment must supply the separately tested filesystem sandbox.

The command emits only the bounded catalog receipt on success and a generic
preserve-evidence refusal on failure. A transport failure or missing output does
not establish whether a catalog commit occurred. Preserve the exact packet and
catalog evidence for diagnosis; do not automatically retry or adopt retained
intents. Historical source freshness remains `not_polled`.

Next deployment gates are the protected launcher, actual catalog-only write
sandbox verification, actual hardened read unit and pinned-image host-socket
acceptance. Installation, activation and real content selection retain separate
operator decisions. No new service or content is deployed by this source change.
