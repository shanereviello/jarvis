# Existing capability map

Inspected source main `dd358de0283d014054c4166ad2c3e564bfbcb49a`; deployed immutable
runtime `workflow-a3f3c05a536a` from source971b7f8. Links refer to source, not mutable
private production configuration. No root data/config contents were exported.

| Capability | Existing implementation | Needed extension |
| --- | --- | --- |
| Repository registration and scope | v1 contracts, `repository_admission.py`, `operator_control.py`; exact SHA-1 baseline/path/recipe binding. | Engineering intake must describe unregistered repositories without granting managed execution admission. Enrollment stays separate. |
| Revisioned work | `workflow-v1.schema.json`, `workflow_records.py`: stable wrk ID, registration digest, revision chain; repository immutable across revisions. | Session links, rationale, criteria, document versions and cross-repository grouping. |
| Attempts and modes | v1 `interactive`, `approval_driven`, `delegated`; attempts bind exact work digest, registration and mode. | One work item can span interactive and managed contexts, but adapters must honor v1 mode/revision bindings rather than appending a different-mode attempt to the wrong work snapshot. |
| Evidence/decisions | Artifact digests/purpose/visibility; append-only chained events, decision subjects and correction references. | Document manifests, field-level evidence references, explicit recording of scoped human acceptance and action prerequisites. |
| Durable storage | `workflow_journal.py`: owner-only0700 store, SQLite0600, atomic records/artifacts/outbox, idempotent duplicate handling, immutable-row triggers. | Authenticated non-root client intake and longer-term capacity/retention; current bounds10,000 records,4MiB/artifact,16MiB supplied artifacts/batch. |
| Managed authority | Root capture/review/one-use approval, admission/config freshness, fixed UID996 slot and protected jobs. | Deterministic review document digest must join protected capture and approval; existing approvals must not be silently reinterpreted. |
| Managed results | Protected finish/imported worker claim, native snapshot observation, isolated independent validation, source-only handoff, frontend GitHub receipts. | Completion document with curated intent/change/rationale and explicit evidence links. |
| Interactive imports | Generic `import-interactive` accepts explicit interactive records with imported/human_reported provenance. It is not universal session observation. | Start/attach/checkpoint/handoff/close client and safe buffered intake without sudo per note. |
| Jarvis reads | `workflow_read_tools.py` exposes bounded pages/history from explicit sanitized snapshots only. | Search, curated narrative documents and allowlisted change/PR references; new public projection contract. |
| Current public view | Omits objective, event free text, actors/source/reference payloads, paths and private artifact bytes. | Publication policy for curated text, labels, supersession/redaction and reader authorization. No automatic secret-redaction claim. |
| Browser | No dedicated engineering web UI or authenticated control API. | Authenticated read service first; separate narrow action gateway later. |
| Ledger | Local durable outbox exists; production activity ledger remains stopped. | Optional indexing backend later; no assumption that it is needed for history or execution. |

Code references: [contracts](../../contracts/workflow-v1.schema.json),
[record validator](../../tools/rras_native/workflow_records.py),
[journal](../../tools/rras_native/workflow_journal.py),
[operator control](../../tools/rras_native/operator_control.py),
[projection-only reader](../../tools/rras_native/workflow_read_tools.py).

Important compatibility facts: v1 rejects extra record properties and unknown kinds;
new session/document fields cannot be slipped into v1 records. Events/attempts link
exact work revision digests. Repository identity cannot change in a work revision.
Filtered histories are not complete inputs for whole-history validation. A valid
provenance label is not authentication. Hash chains do not prevent database-owner
replacement or tail truncation without external anchors.
