# Explicit repeatable managed-history receiver

The source client `engineering/tools/rras_history/managed_sync_cli.py` receives
reviewed private handoffs from the separately approved root exporter. It is an
operator-driven receiver, with no timer, source polling or automatic lifecycle
trigger. It requires an already-created, exact engineering work revision; it never
creates or revises work, invents narrative, renders documents or grants authority.
It is not installed as a global command by this source change.

## Operator sequence

Run the source client with the reviewed Python environment and dependencies.
All paths below are absolute operator-selected private paths. Keep these artifacts
out of Git. First review the work request, packet and fixed service identity, then:

```text
managed_sync_cli.py init --state STATE --work-request WORK_JSON --packet PACKET_JSON --socket SOCKET --service-uid SERVICE_UID
managed_sync_cli.py inspect --state STATE --handoff HANDOFF
managed_sync_cli.py apply --state STATE --handoff HANDOFF --capture-sha256 REVIEWED_SHA256
managed_sync_cli.py status --state STATE
```

`init` checks the existing history head through the peer-verified Unix transport
and fixes the work/source revision binding and endpoint in new private local state.
It writes no history records. `inspect` validates the complete handoff locally and
returns its content digest and counts. Review that exact capture before `apply`;
a digest mismatch refuses before delivery. A digest binds selected bytes, not the
identity or authorization of whoever supplied them. The user-owned handoff is
editable; the retained root original remains the comparison anchor.

`apply` rechecks the engineering head, freezes every page locally before the first
submission, then delivers only imported checkpoints. Stable event keys preserve
existing receipts across overlapping full exports. Source provenance and decisions
remain quoted claims; they do not become fresh observations or execution approval.
No source journal, Git remote, provider credential or control route is accessed.

After an interrupted response, preserve the private state and explicitly run:

```text
managed_sync_cli.py resume --state STATE --capture-sha256 REVIEWED_SHA256
```

Resume uses frozen inputs even if the original handoff is unavailable. Exact
server replay returns the original receipt after a committed-but-lost response.
Saved verified receipts avoid resubmitting completed pages. Incomplete or altered
files refuse and remain available for diagnosis; the client does not repair or
retry them automatically.

## Bounds and interpretation

Each capture must contain all pages of one frozen snapshot beginning at cursor
zero. Packet digests, scope, baseline, work/repository/revision, page chain and
final cursor must agree. A later capture must include unchanged claims for every
previously completed event and cannot regress the completed cursor. A newer
engineering revision requires a new explicit binding; it is not silently adopted.

Private owner-only state uses a nonblocking process lock for delivery. Completed
status revalidates frozen inputs, page plans, receipts and completion summaries.
Limits are 101 pages, 1.5 MiB of canonical capture input and 128 retained captures
per state directory, in addition to existing service/export bounds. No automatic
pruning is supplied. Status reports `source_freshness=not_polled`; a completed
cursor establishes receipt storage for that snapshot, not current source freshness,
task success, merge approval or deployment. Release status remains `not_inferred`.

The initial acceptance included offline loss/replay, multi-page freezing, revision
and scope refusal, concurrent receiver exclusion and damaged-state tests. A live
unprivileged replay of an already approved capture left the history record count
unchanged. This does not test a new coding run or automatic root-to-history wiring.
Protected review-document binding, curated Jarvis publication, automatic lifecycle
integration and GUI/web controls remain subsequent work.


## Complete-handoff setup and pending visibility

The source CLI also accepts `init --handoff HANDOFF` instead of `--packet`.
Every page, digest, scope, work binding and cursor is validated before contacting
history or creating the receiver state. The existing engineering work head must
still match; setup never creates or revises work and writes no history records.
Its returned capture hash is the exact digest to inspect and review before apply.

The offline review-tools entrypoint adds an `events` mode forwarding this CLI:

```text
review_tools_entry.py --manifest-sha256 PACKAGE_SHA events init --state STATE --work-request WORK_JSON --handoff HANDOFF --socket SOCKET --service-uid SERVICE_UID
review_tools_entry.py --manifest-sha256 PACKAGE_SHA events inspect --state STATE --handoff HANDOFF
review_tools_entry.py --manifest-sha256 PACKAGE_SHA events apply --state STATE --handoff HANDOFF --capture-sha256 REVIEWED_SHA256
review_tools_entry.py --manifest-sha256 PACKAGE_SHA events status --state STATE
review_tools_entry.py --manifest-sha256 PACKAGE_SHA events resume --state STATE --capture-sha256 REVIEWED_SHA256
```

This mode requires a newly built and reviewed package. It is not added to an
existing immutable release or installed by the two previously deployed review
wrappers. Trusted root fact export remains separately selected and approved; there
is no new root permission or automatic trigger in this client change.

Status includes `pending_captures`: frozen capture identity, source cursor, event
count and verified locally saved receipt count. It also identifies incomplete local
setup without claiming delivery. A response lost after commit can leave server
records present with zero saved receipts; explicit resume reconciles the original
receipt. Pending input/receipt tampering refuses rather than reporting success.
Source freshness remains `not_polled` even when no captures are pending.
