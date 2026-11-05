# Installed engineering-history operator runbook

This is the day-to-day path for the deployed service, explicit interactive client,
managed imports and curated Jarvis retrieval. See the
[implementation status](engineering-history-implementation-status.md) for deployed
boundaries and the [accepted backlog](engineering-history-phase1/backlog-and-acceptance.md)
for unfinished work. Older source-slice guides describe their original rollout,
not an instruction to install another service.

## What records what

| Record | Purpose | How it advances |
| --- | --- | --- |
| Root workflow journal | Managed execution, validation and decision evidence | Protected workflow commands; separate execution approval |
| Private engineering history | Work intent, sessions, checkpoints, outcomes and immutable documents | Explicit operator client or reviewed managed import |
| Curated catalog | Selected summaries Jarvis may search/read | Exact preview review and separate bounded publication |

A change in one does not automatically update the other two. No command here starts
coding, merges a PR or deploys software. A reported outcome is not authenticated
human acceptance. Current Codex conversations are not automatically collected.

## Start recording a real interactive work item

Run installed client commands as your operator account, without sudo. Inputs and
state stay private and outside Git. In examples below, uppercase variables mean
explicitly selected absolute paths or IDs; do not paste them before setting them.
Use one fresh caller-owned directory with mode 0700 for each independent client
context. The installed client creates its own private spool within that directory.

```sh
umask 077
mkdir -m 700 "$CLIENT_STATE"
rras-history-client init --state "$CLIENT_STATE" \
  --service-socket /run/rras-engineering-history/service.sock --service-uid 995
rras-history-client start --state "$CLIENT_STATE" --key start-1 \
  --request "$WORK_REQUEST"
rras-history-client status --state "$CLIENT_STATE"
```

`WORK_REQUEST` is a reviewed `engineering-history.v1` `work.create` envelope:
repository ID, new stable work ID, revision 1, title, objective, rationale,
acceptance criteria, allowed paths and baseline. Use the existing
[contract example](../contracts/examples/history-local-work.json) for its shape,
but replace its explicitly synthetic content and identities for real work. The
[contract guide](engineering-history-local-foundation.md) explains provenance.
Do not invent a Git baseline or a known occurrence time.

The client pins its transport at initialization. `start` queues the work definition
and session attachment together before delivery. The status context contains the
`work_item_id` and exact `work_revision_sha256` needed to resume later. Keep those
with the private work request and client-state path. They are associations, not
current repository admission or proof that Git still matches the baseline.

Supply `--session-id` only when it is reliably available. Otherwise omit it: null
is the correct representation of an unknown session ID. Do not substitute a shell
PID, timestamp or generated UUID and label it a real Codex session identifier.

## Capture a checkpoint, handoff or reported outcome

Write a bounded structured note JSON and select a new stable action key:

```sh
rras-history-client checkpoint --state "$CLIENT_STATE" --key checkpoint-1 \
  --note "$CHECKPOINT_NOTE"
rras-history-client handoff --state "$CLIENT_STATE" --key handoff-1 \
  --note "$HANDOFF_NOTE"
```

Checkpoint notes contain `checkpoint_type`, `summary`, `decisions`, `next_action`
and `references`. Handoff and pause notes use the same fields except
`checkpoint_type`, which the command fixes. Summarize what changed, why, evidence,
uncertainties and the next step; do not paste credentials or raw transcripts. See
[handoff shape](../contracts/examples/history-interactive-handoff.json).

```sh
rras-history-client finish --state "$CLIENT_STATE" --key finish-1 \
  --note "$FINISH_NOTE"
```

Finish accepts an explicitly reported outcome, summary and references; see the
[example](../contracts/examples/history-interactive-finish.json). It does not close
the conversation, authenticate human acceptance, prevent further notes, infer a
merge/deployment or establish that every acceptance criterion passed. Keep unfinished
work open with a checkpoint/handoff instead of reporting completion.

An action key identifies the same exact input within one client state. Repeating
that key with identical input reuses the saved action and receipts. Changed content
requires a new key. Do not assign a new key merely because a response was lost.

## Resume the same work in another real session

Keep the work ID and exact revision digest, not just its title. Either reuse the
existing private state after inspecting `status`, or initialize a fresh state for
a new independent client context and attach explicitly:

```sh
umask 077
mkdir -m 700 "$RESUME_STATE"
rras-history-client init --state "$RESUME_STATE" \
  --service-socket /run/rras-engineering-history/service.sock --service-uid 995
rras-history-client attach --state "$RESUME_STATE" --key attach-1 \
  --work-id "$WORK_ID" --revision-sha256 "$WORK_REVISION_SHA256"
rras-history-client status --state "$RESUME_STATE"
```

A stale revision refuses on delivery. Inspect the actual scope and obtain an
explicit current attachment; never edit queued requests or silently substitute a
new revision. Different client contexts have different action-key namespaces; use
`flush` on the original state to recover its pending requests rather than copying
them into a fresh state.

## Pending delivery and recovery

A zero exit alone is insufficient. Inspect the returned JSON and saved status:

- `recording_state=recorded`, `pending=[]` and `context_recorded=true` establish
  delivery of the selected association at some time, not current Git/task success.
- `pending` means local persistence without a confirmed receipt for those requests.
  A server commit can precede a lost response; absence of a receipt is not absence
  of the record.
- `incomplete` means abandoned unresolved delivery remains visible.
- `context_freshness=not_polled` means the client did not revalidate live scope.

```sh
rras-history-client status --state "$CLIENT_STATE"
rras-history-client flush --state "$CLIENT_STATE"
```

For an intentional offline checkpoint use `--queue-only`, then preserve the state
and explicitly flush later. Flush replays passive intake only; it never reruns a
worker, merge or deployment. Preserve refused/stale inputs. The supported `abandon`
command requires a reason and records uncertain disposition; it is not a delete,
server undo, approval reset or task cancellation. Never delete a spool to repair
pending telemetry.

## Managed tasks: refresh engineering history explicitly

Use the [managed refresh procedure](engineering-history-managed-refresh.md) to
prepare a digest-bound proposal for an exact operational work revision and obtain
a reviewed protected read-only export. Root export and private operator import are
separate steps; do not improvise a new root database reader or widen its allowlist.
For a new managed receiver, the engineering work must already exist:

```sh
rras-history-managed-sync init --state "$SYNC_STATE" \
  --work-request "$ENGINEERING_WORK_REQUEST" --handoff "$HANDOFF_DIRECTORY" \
  --socket /run/rras-engineering-history/service.sock --service-uid 995
rras-history-managed-sync inspect --state "$SYNC_STATE" --handoff "$HANDOFF_DIRECTORY"
rras-history-managed-sync apply --state "$SYNC_STATE" --handoff "$HANDOFF_DIRECTORY" \
  --capture-sha256 "$REVIEWED_CAPTURE_SHA256"
rras-history-managed-sync status --state "$SYNC_STATE"
```

For interrupted delivery, inspect pending status and explicitly resume the same
frozen capture with `resume --state ... --capture-sha256 ...`. A later root snapshot
gets its own capture ID; overlapping events retain stable source keys and receipts.
These are imports, not independently observed task outcomes or human authority.
No automatic lifecycle trigger or polling freshness is implied.

## Retain the protected review document

The installed `rras-history-review-export` root command produces a separately
reviewed private handoff from an existing protected review. Use its reviewed pinned
procedure for the selected source; no blanket sudo export is implied. On the
operator side, inspect the packet and exact digest before preparing intake:

```sh
rras-history-review-document inspect --packet "$DOCUMENT_PACKET"
rras-history-review-document prepare --state "$DOCUMENT_STATE" \
  --packet "$DOCUMENT_PACKET" --packet-sha256 "$REVIEWED_PACKET_SHA256" \
  --socket /run/rras-engineering-history/service.sock --service-uid 995
rras-history-review-document apply --state "$DOCUMENT_STATE" \
  --packet-sha256 "$REVIEWED_PACKET_SHA256" --approve-private-document
rras-history-review-document status --state "$DOCUMENT_STATE"
```

Use [the exact-document guide](engineering-history-review-document-commands.md)
for prerequisites and interrupted-delivery resume. Storing an immutable reviewed
document preserves bytes and provenance; it does not create an execution grant.

## Inspect privately and share only selected summaries

The explicit client `status` shows delivery/context, not a searchable database UI.
The authorized history/document Unix read API provides private records and exact
Markdown/manifest retrieval. The service database remains private to its service
identity; do not change ownership or connect a desktop database client directly to
production SQLite. The deployed read-only dashboard presents authorized history
through the service socket; it is not a dependency for explicit recording.

Jarvis can use `engineering_history_search` and `engineering_history_read` through
its installed `rras-curated-history` MCP entry. Ask for the curated history relevant
to a change, with source references and limitations. An empty search is not proof
that no private engineering record exists.

To share new material, build a private explicit selection from exact history
receipts, review its summaries/rationale/limitations and preview digest, then use a
reviewed hash-bound root publication procedure. The installed
`rras-curated-publication` accepts only a protected preselected request digest;
it is not a general unprivileged narrative uploader. Root staging and publication
need the appropriate explicit decision. Private intake alone does not publish.
Keep old generations and receipts; a withdrawal changes the current view and makes
old cursors invalid. Do not cache or repeat content after a stale/refused read.

## Installed client acceptance so far

On November 3, 2026, the operator-account client recorded a real runbook work item,
its explicit attachment and a progress checkpoint through the installed service.
The checkpoint was first queued locally; a private service read confirmed it was
not yet delivered. A later CLI process flushed one record, and repeating the
original action reused its receipt without a duplicate server record. Three work
records were present after replay. No curated content was published and no worker
ran. The native session ID was unknown. This is actual service/client-process
acceptance, not proof of separate native Codex sessions.

## Real-session acceptance checklist

Local tests and independent CLI processes establish replay/transport semantics;
they do not prove real desktop/server session continuity. For one actual work item:

1. In session A, record the work, a real checkpoint and a handoff. Save work ID,
   revision digest, client-state path and acknowledged receipt IDs privately.
2. In a separately opened real session B, explicitly attach the same work/revision,
   read the private prior record through authorized service access, and continue
   from its actual next action. Record whether the session identifier is known.
3. Save a second checkpoint/handoff. In real session C, resume the same association
   and verify the earlier notes and any selected immutable documents remain retrievable.
4. Queue a bounded passive note without delivery, restart only the client process,
   then flush the same state. Verify one new server record and the original receipt
   on replay. Do not stop the production service or retry any engineering action
   to manufacture an outage scenario.
5. Record observed receipts/counts and operator-reported session transitions
   separately. A claimed session label, null ID or agent summary is not a native
   authenticated session event. Leave the criterion pending if not actually done.

The acceptance record must distinguish installed-command checks, local fixtures,
actual service writes and operator-confirmed real sessions. It must not claim
success for future transitions. This runbook installs no hook, timer, listener,
GUI, automatic transcript collector or paid task.


## Read-only dashboard operations

Use the configured HTTPS hostname through Cloudflare Access. The dashboard runs as
UID993 and can read only the configured `jarvis` history repository; it cannot
submit notes, approve work or execute actions. Overview uses the latest work
revision, timeline uses recorded events/provenance, documents use stored immutable
Markdown/manifests with digest checking, and evidence lists recorded GitHub links.
Links are not live verification of remote facts. There is no separate web database.

The canonical private store is `/var/lib/rras-engineering-history/history.sqlite3`;
only history UID995 opens it. The web process uses
`/run/rras-engineering-history/service.sock`. Access policy is
`/etc/rras-engineering-history/access-policy.json`; dashboard configuration is
`/etc/rras-engineering-history-web/config.json`. Keep configuration and private
records out of Git. The dashboard release is
`/opt/rras-engineering/releases/history-web-9e150671dcfa`.

Read service state without changing it:

```sh
systemctl show rras-engineering-history-web.service \
  --property=ActiveState,SubState,MainPID,UnitFileState
systemctl show rras-engineering-history.service --property=ActiveState,MainPID
```

For browser failures, distinguish DNS resolution, Cloudflare/tunnel origin
connectivity, Access login and application authorization. The reviewed route uses
HTTP to the private host bridge on port18764; browser traffic uses HTTPS and the
connector travels over the encrypted tunnel. An unsigned origin API request is
expected to return403. It is not proof of authenticated document retrieval.
Never disable Access or bypass signed-token checking to diagnose a502.

History-service outage/revocation must show unavailable rather than cached private
history. Inspect the original client spool/status for pending recording; flush the
same passive requests rather than rerunning coding or deleting state. Preserve
protected installation/activation journals before investigating partial upgrades.
Changes to protected config/policy, service restarts, upgrades and recovery require
their own reviewed procedure; do not replay a successful first-activation script.
Do not restore the database to fix a deployment receipt. Backup/restore remains
operator-deferred, so no tested recovery guarantee is claimed.

The dashboard and Jarvis have distinct readers. Jarvis's MCP tools currently expose
only the explicitly curated catalog, not the dashboard's private records. See the
[closeout backlog](engineering-history-dashboard-closeout.md#deferred-backlog)
before designing broader access or automatic publishing.
