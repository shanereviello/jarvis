# Selected-source capture and delivery

The passive adapter freezes normalized exports and exact reporting requests in a
caller-owned private spool. It calls only the history `evidence_upload` and
`reporting_submit` methods. Collection and replay never launch engineering work.
This source does not activate a collector, install hooks, or enlarge a grant.

`capture_jobs.py` provides `init`, `run-once`, and `status`. A future operator
timer can invoke `run-once`; each pass is bounded, locked against concurrent
collectors, and independent of an interactive desktop session. Configuration is
an exact owner-only JSON file with contract `engineering-capture-jobs.v1`,
`spool`, `service_socket`, numeric `service_uid`, and one to 32 `jobs`. Each job
has `id`, exact canonical `source` and `binary` paths, native `session` UUID,
`scope`, exact reporting `context` (or null), and an attributed
`authorization_reference`. No source discovery, wildcard directory, environment
credential, or repository-to-project inference is supported. A reference records
the selection basis; it is not independent authentication of human consent.
A v2 job configuration additionally requires an explicit `source_segment` for
each selected source. Segments sharing a native session are separate artifacts
with independent byte ranges and revision chains; the native session identity is
preserved. A repeated segment identity is rejected. The existing v1 format and
its artifact identities remain unchanged. Segment identifiers do not establish
that every native file was selected or that a segment belongs to a work item.

The Codex adapter pins SpecStory 2.17.0 executable SHA-256
`25b8a1b7c13b6cccd514845608785057b980ad3d55029d75527a0d9aaf0603c4`.
It copies only the selected complete native JSONL prefix into a private temporary
HOME, relocates session metadata to a temporary Git repository and runs session
filtered `sync --print` with cloud, telemetry, analytics and version checks
disabled. It does not copy account configuration or change real hooks/worktrees.
Its temporary raw input/output are private and removed after staging; the native
original stays under its original owner. Coverage is partial: response-item-only
fixtures can produce no visible conversation despite a successful collector exit.
An empty export or unmatched visible messages remain disclosed capture gaps.

Hermes reuses its pinned native Markdown exporter
`750953cd48cd8cf7435a1c7427f5ff3e1c5d10fda9519cc7a4d3889e7d1b2ffa`.
`selected_hermes` accepts an **already initialized** native reader inside the
existing Hermes boundary. It never constructs/migrates SessionDB, searches other
sessions, or opens private configuration. It reads the selected conversation's
native compression lineage, including compacted display rows and excluding
rewound/deleted rows. More than 64 segments or 10,000 messages refuses capture
without deleting source. `collect_hermes` invokes native force redaction before
rendering, filters system/developer messages and explicit analysis/reasoning
channels/fields, then applies the owned intake filter. This API has not been
installed as a Hermes hook and does not grant Hermes private history access.

The separate `hermes_readonly.py` entry can construct the inspected native
`SessionDB(read_only=True)` inside the Hermes boundary. Its exact reader source
is pinned; that native branch opens `mode=ro`, skips schema initialization,
repair and writer startup, and closes without requesting a WAL checkpoint. One
SQLite read snapshot covers the selected metadata, compression lineage and
messages. It requires an initialized canonical database path and an exact ID;
it never uses native prefix resolution. Native Linear aliases of the form
`linear:<organization UUID>:<session UUID>` are supported as identities, not paths.

`probe_hermes_native.py --isolated-containers` passes using the installed Hermes
code in a disposable offline container. A newly created synthetic source retains
visible messages across native compression, excludes another session and private
reasoning, and leaves database bytes unchanged. The real native context bindings
also pass; spoofed process environment variables do not substitute for a bound
API run. No real Hermes history is exported and no models run in this probe.

The owned `engineering-redaction-v1` profile removes recognized authorization,
cookie, credential, provider-key, JWT and private-key patterns **before retained
export writes**. It is not proof that arbitrary secrets are absent. Exports remain
operator private. Explicit native reasoning channels are excluded; visible
engineering explanations and tool diagnostics remain evidence, not instructions.

Source digest/range, native source times, optional capture time and selection
reference, collector version, export digest, coverage gaps and exact intake
receipts are retained separately. Session context does not establish that every
exchange belongs to one work item. Unknown associations remain unmapped.
Unchanged source is deduplicated before rendering (native exports embed time).
Changed source appends a version with its exact predecessor. Native prefix
replacement/shrink is disclosed; prior exports remain immutable.

The spool retains requests, exports and chunk receipts across interruption,
service outage and lost acknowledgments. Receipt/digest mismatches stay pending.
Capacity is 1 GiB retained exports and 10,000 queue items; no automatic deletion
is enabled. Reserved status capacity prevents a failed delivery status from
rolling back an accepted artifact receipt. Missing/corrupt source and delivery
failures have sanitized, deduplicated states. Restore/backup must include both
the queue database and exports. The service separately enforces evidence quotas.

Synthetic tests cover actual pinned SpecStory execution, the installed native
Hermes renderer/force-redaction helper, immutable version replay, selected source
guards, redaction before persistence, unknown associations, queue capacity,
corrupt exports, wrong/lost receipts, restart and outage recovery. Actual Hermes
session collection and scheduled collector activation still need their selected
source authorization and deployment acceptance. Prior real-session permission
applies only to the explicitly approved chat pilot.

## Selected chat intake — November 10, 2026

The operator separately authorized one private intake of this chat. The installed
v2 collector retained its three explicitly selected native files as separate
unassigned artifacts and received all chunk and reporting receipts. No scheduled
capture or model execution was enabled. The artifacts have partial coverage:
full-text comparisons to the redacted exports left 30 visible source messages
unmatched in the November 6 file and 22 in the November 8 file; normalization
may also prevent verbatim matches. No visible source message was unmatched in
the November 4 file under that comparison. Reasoning is excluded, and complete
tool/media coverage is not established.

The first stored chunk of each artifact passed a scoped API digest readback. A
full 171-chunk readback was stopped after several minutes; whole-artifact
readback remains unverified. Each chunk upload and the artifact manifest did
receive matching custody receipts. The records are unassigned because the chat
covers multiple efforts; its artifacts do not assert a single work membership.
