# Managed workflow links: first source slice

The operational workflow and private engineering history are deployed separately.
This slice adds a bounded bridge in source; no exporter, delivery service, schedule,
privileged permissions or history runtime upgrade is installed by its merge.

## Identity and authority

Use the same stable work ID and repository ID in both stores. An explicit mapping
binds the exact operational work-record SHA/revision to the independently reviewed
engineering work-body SHA/revision. Baseline and ordered scope paths must match.
Do not silently overwrite an existing engineering revision or assume its revision
number equals the operational revision. A changed head requires a new explicit
mapping; stale heads refuse at normal history intake.

`engineering_export.py` reads a consistent transaction using SQLite mode=ro and
query_only. It validates the complete operational history, then exports one exact
work revision and a bounded page of its events. It writes no source records,
artifacts, approvals or cursor state. A caller selects the source journal label;
that label and packet digests detect inconsistency, not authenticity.

Export fields are explicitly allowlisted: work/repository/revision/mode, baseline,
relative scope, source digests, event/attempt/correction IDs, event types/outcomes,
original timestamps/provenance/ingestion, artifact IDs/digests/purposes, and
conservative credential-free commit/PR references. Omitted references are counted
explicitly, including private/unsupported forms and the per-event reference cap. Raw artifacts, event summaries,
objectives/prompts, actors, registration paths, profiles/config and full private
references are omitted. Artifact digests may themselves be private metadata; all
packets and imports remain operator-private. No URL is fetched.

The importer produces ordinary imported `checkpoint.append` records compatible
with the installed v1 store. Source fact fields are quoted inside deterministic
summary content and linked by digest. They do not become new authenticated observed
facts or human approvals. Approval/validation/merge/deployment remain distinct event
types; `release_status` remains `not_inferred`. A checkpoint's own occurrence time
is unknown; known source timestamps remain explicitly quoted inside it.

## Delivery, replay and privacy

`link_delivery.prepare` exclusively creates caller-owned0700 state and immutable
600 plan bytes. It never creates/revises the destination engineering work; that
explicit work revision must already be present. Delivery regenerates the plan,
verifies association, submits only passive checkpoints and saves durable receipts.
It verifies writer/peer IDs, request/head hashes and private imported/no-authority
provenance. No approval, coding, GitHub, deployment or root-journal action occurs.

Initial pages start at source cursor0. Later pages require a matching completed
prior state and exact cursor/binding. A complete cursor is written only after all
receipts are durable. Lost response or lost local receipt recovers through the same
stable request key, not a repeated engineering action. Overlapping export pages
produce the same request. Changed event content under the same identity conflicts.
Source event order is preserved; source and history sequence numbers are distinct.
Corrections remain separate links; no imported prior record is edited/deleted.

Hashes/allowlists do not authenticate caller-authored packets. Actual protected
export custody and source-to-client handoff need the following root host acceptance
and separately reviewed installation. Ordinary callers cannot gain authority by
forging a packet, receipt or provenance label.

## Explicit source commands

Use the reviewed dependency environment. Paths are examples, not deployment steps.
Do not execute source code under sudo without the separately pinned host procedure.

```
engineering_export.py --store PRIVATE_SOURCE --journal-id REVIEWED_LABEL \
  --work-sha256 EXACT_OPERATIONAL_REVISION_SHA --output PRIVATE_PACKET
managed_link_cli.py prepare --state NEW_PRIVATE_STATE \
  --work-request EXACT_ENGINEERING_WORK_REQUEST --packet PRIVATE_PACKET
managed_link_cli.py deliver --state PREPARED_STATE \
  --socket REVIEWED_SOCKET --service-uid REVIEWED_SERVICE_UID
```

For later pages, prepare additionally requires `--previous-state COMPLETE_STATE`.
The private input files must be caller-owned regular600 files. The source journal
requires its owner (root in production); exporter output remains private to that
owner. No root-to-operator permission handoff is implied by these source commands.

## Validation and next gates

Disposable real SQLite tests cover unchanged source bytes, exact revision/scope,
allowlist/private-text exclusion, imported provenance, no new store schema, packet
and receipt tampering, cursor chaining, stale head refusal, partial failure and
lost-response/idempotent replay. These are source semantics, not production
end-to-end integration acceptance.

Next: separately reviewed protected exporter package and distinct-UID handoff
acceptance, operator-reviewed mapping for the existing managed acceptance task,
explicit private import/readback, then managed lifecycle/export wiring. No paid
run is required to validate this passive bridge. Protected review-document binding,
Jarvis narrative publication and GUI remain later slices. Existing interactive work
is not automatically migrated, imported, or exported by this source change.
