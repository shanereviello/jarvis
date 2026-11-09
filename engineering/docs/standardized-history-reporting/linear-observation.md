# Passive selected-project observation

`linear_observer.py` imports project, issue, comment and document snapshots from
one explicitly selected Linear organization/team/project. It follows native
`first`/`after` cursors for issues, each issue's comments and project documents.
Every pass starts at page one; stable object/content/context keys tolerate
overlap. More than 1,000 pages per connection, repeated/empty advancing cursors,
GraphQL partial errors, missing selected parents and wrong OAuth actor or scope
produce an explicit gap. Already frozen observations survive a partial pass.

Project and document context is explicit project context. Issue/comment context
comes only from the installed issue-to-work mapping; new unmapped issues remain
unmapped. No issue state, comment or document automatically starts work, assigns
a project, records a human approval or changes Linear. Polling cannot recover
every intermediate edit or an object deleted between polls.

Small snapshots are canonical JSON, with strings recursively redacted **before
JSON escaping** and before queue persistence. The original source digest,
normalized snapshot digest, source update time, import receipt, selected IDs and
coverage/redaction limits remain separate. Normalized snapshots over 64 KiB are retained as immutable, chunked JSON
evidence. The bounded observation contains an explicit artifact reference and
digests; it does not silently truncate the original. Exports exceeding the
evidence limit remain a reported gap. Session transcripts use the same custody
boundary with their own source identity and coverage limitations.

The existing gateway was not assumed to provide complete pagination.
`n8n_linear_observer.py` instead renders an **inactive** four-node narrow reader
using the existing separately attributed Codex OAuth credential. An additional
private header-auth credential protects the reader. It accepts only operation,
object ID and bounded page cursor, constructs fixed GraphQL queries itself and
checks actor/organization/project/team before returning data. Comment reads are
nested under the selected project and exact issue filter, so arbitrary issue
UUIDs cannot return another project's comments. No arbitrary GraphQL, mutation,
destination URL, provider credentials or private history mount is accepted.

`linear_observer_http.py --config <private-job.json>` performs one passive
collection/delivery pass. Its exact `engineering-linear-poll-job.v1` configuration
has `spool`, `reader_url`, `reader_token_file`, `service_socket`, `service_uid`
and `selected`. The selected binding has `organization_id`, `team_id`,
`actor_id`, `project_id`, `scope`, project-only `context` and explicit `issues`
contexts. Files and spool are caller-owned/private; the endpoint path pins the
selected project. The transport sends only read parameters and the dedicated
bridge header, never exports n8n's OAuth token, and follows no redirects.
Collection takes the spool's exclusive lock and waits for another collector to
finish; the systemd service timeout remains the upper bound. Replay calls only
the scoped history upload/reporting methods.

Generated Code nodes pass actual Node execution tests for read construction,
pagination parameters, arbitrary-query refusal, OAuth identity and scope checks.
Synthetic history/HTTP tests cover full pagination, comment/work association,
unknown work, recursive redaction, unchanged replay, retained partial passes,
outage recovery, wrong identity and stuck cursors. A separately unpublished
read-only n8n diagnostic verified the actual Codex OAuth actor and selected
project's metadata, document connection and filtered issue/comment query fields.
It preserved all seven previous workflow records, performed no Linear mutations,
exported no credentials and started no models. This is schema compatibility,
not production scheduled-poller or complete historical-coverage acceptance.

The selected production reader, bridge credential, passive timer and reporting
schema were activated in November 2026. A complete poll and delivery were
verified after the oversized-document fix; later overlapping polls completed
without new records. n8n remains the OAuth owner and the reader uses the private
integration network. This does not prove capture of intermediate edits or
between-poll deletions.

Official API behavior: [GraphQL errors and authentication](https://linear.app/developers/graphql),
[Relay-style pagination](https://linear.app/developers/pagination).
