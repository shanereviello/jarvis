# Additive reporting metadata contract

`engineering/tools/rras_history/reporting_contract.py` defines and validates
**engineering-reporting.v1**. Source now also implements the immutable metadata
stream, explicit owner-only schema-v4 upgrade, scoped Unix dispatch and signed
four-stream reads. This is not deployed. Existing v1/v2 work, v1 project and v1
scope envelopes remain unchanged.

Every envelope has an explicit scope, stable client event key, attributed source,
nullable source event time, exact prior reporting-record digest when applicable,
and a typed operation body. Source times stay separate from eventual receipt time.
No field grants human approval, execution, deployment or independent verification.

Mapped context pins project ID, architecture document/version/digest, and optional
work ID/revision/assignment digest. Only captures, observations and freshness can
remain explicitly unmapped. The store must resolve these pins against retained
owned records; shape validation alone does not prove that those objects exist.

| Operation | Retained relationship |
| --- | --- |
| `mapping.record` | Versioned Linear organization/team/project/issue UUIDs and display references; execution plan ID versus project/decision/grouping identity. Only execution mappings carry a work context. |
| `attempt.record` | Versioned run phase, actual actor/runtime, optional coordinator, sessions, Git baseline and result; attempt completion is not a work outcome. |
| `session.relate` | Exact named session plus explicit attachment, resume, compression, continuation or coordination relationship. |
| `checkpoint.report` | Observations, alternatives/reasons, changes, validation with evidence references, open questions and next step. |
| `linear.observe` | Exact bounded object snapshot, digest, source-update time and selected workspace/team/project IDs. |
| `handoff.record` | Distinct Jarvis/Codex sender and recipient, source/recipient sessions, correlated issue, requested action and truthful request/acknowledgment/result. |
| `decision.observe` | Exact architecture/deviation source text and attributed author; an observation does not designate an architecture or authenticate the human. |
| `artifact.record` | Versioned private-export manifest, content digest, byte count, source range/session, collector/version, explicit completeness/gaps, redaction profile and chunk references. |
| `artifact.associate` | Append-only association/correction referencing an exact manifest and previous association digest; original import remains. |
| `source.observe` | Explicit source/cursor, observed time, delivery/freshness state and gaps, including unmapped or pending evidence. |

Metadata retains the existing 128 KiB envelope bound. A manifest can reference up
to 1,024 contiguous chunks of at most 64 KiB, totaling at most 64 MiB. Chunks are
private export bytes, not base64 transcript fields hidden inside legacy work
requests. No arbitrary file path, fetch URL, launcher command or credential is
accepted as an artifact storage location. Larger exports need explicit ranges/
revisions, not truncation concealed as complete capture.

`reporting.py` resolves context against exact retained project, architecture,
work-revision and membership records. Late observations can name an earlier
retained assignment; today's membership is not substituted. A stable mapping
cannot be reused for unrelated work, execution plan/work/issue duplicates are
refused, and issue mappings require their retained Linear project mapping.
Terminal attempts require a new attempt for retry. Handoff revisions preserve
their exact participants, source context and valid next exchange state.

`reporting_entry.py migration-plan --store ...` computes a fingerprint of prior
schema, work/project/scope records, outboxes and snapshot key. `migrate` requires
that exact fingerprint and schema 3; no implicit chained upgrade or RPC migration
exists. Existing rows, DDL and the signing key remain intact. The new tables are
`reporting_submissions` and `reporting_outbox`, both protected by immutable
triggers. Nothing is seeded or backfilled by the migration.

`submit` uses an exact private request file with either the owner store or scoped
service socket. `read` takes a private file containing `scope` and `query`, with
`query.view` set to `reporting`; existing project/work reads also expose bounded
reporting summaries. Read grants remain read-only. Access is checked before
duplicate lookup, and actual socket receipts retain the kernel peer UID. Exact
retry returns its existing receipt; changed content under the same key is refused.

New view signatures include `reporting_sequence` alongside work/project/scope
boundaries. Earlier two/three-stream tokens keep their original MAC and show
reporting unavailable. Current and closeout project/work views never join later
reporting records. Paging, summaries and counts use only the admitted scope and
the selected signed boundary.

Private chunk staging/finalization/quotas remain unimplemented. The service
therefore refuses `artifact.record` and `artifact.associate` rather than accepting
a manifest without verified retained bytes. Private evidence files and database
must eventually be backed up together; this source does not complete the earlier
deferred backup/restore work.

There is no direct SQL production insertion or inferred deployment authority in
this source. Artifact intake, automatic observation/capture delivery,
reference UI and curated retrieval remain separate unfinished build capabilities.
