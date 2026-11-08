# Structured reporting publication profile

The existing curated catalog and its two MCP tools remain the retrieval boundary.
`curated_reporting.py` adds a reusable profile for selected repository projects
and exact structured fields. Full transcript bytes, raw Linear snapshots, source
paths and session exports are excluded. No private-history mount or new reader
privilege is given to Hermes. Non-Git publication is outside this initial profile
adapter; operator-private non-Git history/capture remain supported separately.

The profile records stable ID/version, selected project/repository pairs, allowed
operations/fields and the attributed installation approval reference. Its exact
SHA-256 is pinned. Unknown fields, raw snapshot/transcript selections, unknown
profile digests and source/receipt/context mismatches refuse publication. A
repository grant alone does not select every project in that repository.

| Group | Permitted structured fields |
| --- | --- |
| Mapping | Kind, plan ID, Linear references and mapping reason |
| Attempt | Attempt ID, phase, executor/coordinator, baseline, reported result and references |
| Checkpoint | Report/attempt IDs, observations, alternatives/rationale, changes, reported validations, open questions, next step and references |
| Handoff | Handoff ID, sender/recipient, state, issue, requested action, result and references |
| Decision observation | ID, kind/state, attributed author/basis, source reference and statement |
| Capture reference | Artifact ID/version, content digest, completeness, limitations and redaction profile; no transcript bytes |
| Freshness | Last source-observed time, state, gaps and detail |

Only the fields explicitly selected within these groups are published. The owned
redaction profile filters recognized secrets recursively before publication.
That filter is partial, and field policy remains necessary. Supplied source rows
are consistency-checked claims; neither valid digests nor an owner-approved
profile authenticate a human's original decision. Entries retain these limits,
exact source request/receipt, work revision, project and architecture references.
Artifact reassociation does not silently fold an originally unmapped import into
another project's publication; the original explicit context determines eligibility.

`install_profile` through the existing bounded publication entry records one
immutable owner-approved profile under `catalog/profiles/<sha256>.json`.
Installation requires the explicit approval packet and exact reviewed profile
digest. The `engineering-curated-profile-execution.v1` packet then selects that
installed digest, supplied snapshot rows and exact catalog head; it cannot supply
a replacement profile or approve itself. Ordinary checkpoint publication needs
no new per-entry human selection. The packet digest is transport integrity, not
another human approval. No publisher timer is enabled by installing source.

The publisher retains generation/cursor checks and existing repository/UID grants.
Withdrawn entry IDs remain excluded from routine profile publication, including
when a later checkpoint is published. Identical input at the current head creates
no extra generation. Profile changes require a separately installed exact digest;
stop the old configured publisher when narrowing or withdrawing a profile, and
withdraw existing entries using the existing catalog operation. Earlier immutable
profile files and generation records remain available as operator evidence.

The preview returns at most the latest 100 eligible supplied records, with explicit
eligible/returned counts. It is a bounded reference catalog, not the full archive.
No claim is made that a supplied batch is a complete database snapshot. The
existing generation cap still stops publication at capacity; there is no automatic
deletion or recycling. Backups must include profiles and the whole catalog along
with the owned history database, chunks, capture spools and transport state.

Synthetic acceptance runs actual MCP stdio discovery/search/read and the Unix
service under distinct service/reader UIDs in the pinned installed Hermes image.
It verifies exact engineering context, private-field exclusion, other-repository
and action denial, withdrawal/stale-generation refusal and reader revocation.
The disposable container has no network, production mounts, real history,
credentials or model runs. It mounts only repository engineering source read-only.
This proves the protocol path on fixtures, not installation in the live Hermes
tool configuration or live publication of the operator's private archive.
