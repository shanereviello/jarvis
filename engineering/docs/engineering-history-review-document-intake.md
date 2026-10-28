# Exact private review-document intake

The protected document/v2 approval workflow was installed as
`workflow-67682728145f` after PR57's isolated host acceptance. This next source
slice prepares the passive document packet and unprivileged history receiver.
It does not install an exporter, update that workflow or write production history.

## Producer and private packet

`review_document_link.build(custody)` selects an explicit engineering work request,
document request, document manifest, exact Markdown and passive capture companion
from a verified protected document custody object. A trusted root producer must
first load that object through the installed `document_approval.load` boundary.
This constructor itself does not authenticate supplied objects or read root state.

The packet contract is `engineering-review-document-export.v1`, at most 512 KiB.
It has no approval record, token, executable command, live configuration contents
or separate operational mutation payload. The Markdown includes the captured
metadata already frozen for private review, including private paths; this packet
must not be placed in Git, public logs or Jarvis search. Visibility is fixed to
operator_private; source provenance is imported and authority is false.

Validation checks exact field sets, canonical digests, imported document source,
work/revision association and the existing review document contract. It regenerates
the Markdown/manifest against the explicit engineering work and compares exact
bytes, content/template/renderer hashes and companion associations. Unknown or
changed renderer/template semantics fail closed instead of silently replacing
protected document bytes. The companion describes a passive capture association;
it does not prove that a v2 grant was issued, consumed or successful.

An editable caller-owned packet can be forged together with its hashes. Actual
protected source custody and root-to-user handoff still require a reviewed producer
and host acceptance. None of these hashes promote imported claims to observations
or human authority.

## Explicit receiver lifecycle

Use the source API with the reviewed Python/dependency environment:

```python
review = review_document_link.inspect(packet)
review_document_link.prepare(new_private_state, packet, review["packet_sha256"])
review_document_link.deliver(new_private_state, authenticated_call,
                             writer_uid=expected_service_uid, peer_uid=caller_uid)
```

The operator must review the exact selected packet/digest before preparation.
`prepare` creates new caller-owned0700 state with immutable600 input bytes; no
history submission occurs. No global CLI is installed by this source change.
`authenticated_call` must use the existing peer-verified Unix transport and expected
service identity, not caller-supplied peer headers or an arbitrary remote service.

Delivery takes a nonblocking private-state lock and checks that the destination
already has the exact current engineering work-body hash. It never creates or
revises work implicitly, even if the packet contains a work request. The operator
must separately establish/review that work revision. It submits only the frozen
imported `document.render` request, verifies its durable v2 receipt including the
exact document manifest, then reads the exact document version back and compares
Markdown and manifest before writing completion. The source receipt helper now
accepts an optional expected manifest; checkpoint callers still require no document
manifest by default.

After interruption, explicitly repeat delivery using the same saved private state.
A committed-but-lost response reuses the unchanged request key and original server
receipt. A receipt saved before a failed readback is retained; recovery retries
readback without another submit. Completion remains absent until exact readback
passes. Changed packets/receipts/completion files refuse and stay available for
inspection. A changed engineering head refuses; pending old revisions are not
silently adopted. No source operation, approval or coding run is repeated.

## Evidence and remaining gates

Disposable SQLite tests establish exact-byte storage, stable replay, lost response,
readback outage/recovery, false receipt refusal, missing/stale work refusal, packet
schema/digest/provenance tampering and lock exclusion. Existing checkpoint/sync
regressions run with the generalized receipt helper. These tests do not establish
root export custody, a distinct-UID transfer or production intake acceptance.

Next: package a trusted producer using the actual installed protected loader,
rehearse a private cross-UID handoff/intake and obtain explicit approval for a real
selected document/work import. Runtime code updates and any private export/import
retain their separate decisions. Automatic lifecycle capture, curated Jarvis
publication, GUI/web controls and authenticated human approval from those clients
remain later work. No paid run, database migration, new service or backup policy
change is introduced.
