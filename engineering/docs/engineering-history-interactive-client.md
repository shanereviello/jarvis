# Explicit interactive engineering-history client

Source-only local client for the accepted separate-service design. It records
start/attach, checkpoints, pause/handoff and reported outcomes. There is no automatic
Codex session discovery, transcript scanning, hook installation, network listener,
privileged exporter, narrative sharing or execution/merge/deployment action.
The installed root workflow and its journal remain unchanged.

## Two durable local boundaries

The caller-owned history database holds engineering records, receipts and documents.
A separate caller-owned0700 client directory holds `client.sqlite3`0600: fixed local
transport configuration, active intended work context, immutable actions/requests,
acknowledged receipts and explicit delivery dispositions. Both databases use SQLite
FULL synchronous transactions; this is not an authenticated installed service or an
off-host backup. The caller owns and can ultimately replace these files.

An action atomically commits its exact requests and context switch into the client
spool before any history-store call. A start queues work.create then session.attach;
notes queue separately with the exact selected work revision. Flush delivers in
original order and stops at the first unavailable/refused request. The store's
idempotency keys recover a lost response after a backend commit without duplicate
records. A client crash between acknowledgment and local commit likewise leaves the
same request for a later explicit flush. Delivery never invokes coding or GitHub.

## Explicit commands

Use an interpreter with the existing contracts dependencies. Paths below are fresh
private placeholders; the examples are synthetic, not real work/approval records.
The history store and client state must use different directories. Neither command
should run through sudo. Creating a client can select a currently unavailable store,
but it never initializes the backend automatically.

```sh
mkdir -m 700 /absolute/private/history-fixture
mkdir -m 700 /absolute/private/codex-session-fixture
python engineering/tools/rras_history/cli.py init --store /absolute/private/history-fixture
python engineering/tools/rras_history/interactive_cli.py init \
  --state /absolute/private/codex-session-fixture --history-store /absolute/private/history-fixture
python engineering/tools/rras_history/interactive_cli.py start \
  --state /absolute/private/codex-session-fixture --key synthetic-start-1 \
  --request engineering/contracts/examples/history-local-work.json
python engineering/tools/rras_history/interactive_cli.py handoff \
  --state /absolute/private/codex-session-fixture --key synthetic-handoff-1 \
  --note engineering/contracts/examples/history-interactive-handoff.json
python engineering/tools/rras_history/interactive_cli.py finish \
  --state /absolute/private/codex-session-fixture --key synthetic-finish-1 \
  --note engineering/contracts/examples/history-interactive-finish.json
python engineering/tools/rras_history/interactive_cli.py status --state /absolute/private/codex-session-fixture
```

Every mutating intake command needs a stable `--key` identifying that action within
this client state. Repeating the same key and exact input returns the existing action;
changed content with that key refuses. Use a new key for genuinely new work/notes.
Keys are scoped by a generated client identity when mapped to history-store requests.
Retrying an older action never resets a subsequently selected active context.

`start` requires a new work.create request/revision1. `attach` instead joins an
existing work item with its exact current work-body digest:

```sh
python engineering/tools/rras_history/interactive_cli.py attach \
  --state /absolute/private/codex-session-fixture --key explicit-attach-1 \
  --work-id WORK_ID --revision-sha256 EXACT_WORK_BODY_SHA256 --session-id KNOWN_SESSION_ID
```

Omit session-id if unavailable; it remains unknown. No guessed session ID, current
working directory or repository title selects work automatically. A new/resumed
session can use a separate private client-state directory and attach to the same
work/revision. The server-side local store checks the revision on delivery. The
local context is an intended association, not proof that the baseline/configuration
or current Git tree has been verified.

`checkpoint` accepts summary/decisions/next_action/references plus checkpoint_type.
`pause` and `handoff` fix their type and reject a caller-supplied checkpoint_type.
`finish` accepts a supported reported outcome/summary/references. Notes cannot override
work/revision or silently change session identity. To select a different work/scope
revision, attach explicitly. Finish records an outcome claim; it does not close the
Codex conversation, prevent later notes, or establish human deliverable acceptance.
Source narratives remain reports without authenticated human/observed authority.

## Pending and uncertain delivery

Add `--queue-only` to any intake command to persist locally without contacting the
store. Otherwise the command queues then attempts passive local delivery. A zero
exit can mean local persistence with pending delivery; inspect the JSON status,
not merely the exit code. `context_recorded` means an exact matching attachment was
acknowledged sometime; `context_freshness=not_polled` prevents treating it as current
admission or a live Git/status check. `recording_state` is empty/recorded/pending or
incomplete; none is a coding-task success/authorization state.

```sh
python engineering/tools/rras_history/interactive_cli.py flush --state /absolute/private/codex-session-fixture
```

Flush is explicit, not a timer or background model. It retries only passive history
intake using the original keys; it cannot repeat coding, merge or deployment.
`store_unavailable` and `store_refused` are bounded categories, not raw errors/logs.
A stale scope refusal leaves the original request for inspection; do not silently
rewrite its revision to make it pass. A malformed receipt preserves pending requests.

To resolve a consciously abandoned delivery before attaching to a corrected scope:

```sh
python engineering/tools/rras_history/interactive_cli.py abandon \
  --state /absolute/private/codex-session-fixture --key ACTION_KEY_TO_ABANDON \
  --reason engineering/contracts/examples/history-interactive-abandon.json
```

This is local delivery bookkeeping, not worker cancellation. It preserves the exact
requests and any known receipts, records an immutable reason/time, and skips only
unresolved requests for that action in later flushes. It explicitly does not infer
that the store never committed them, undo a store write, or erase acknowledged
history. The overall client state stays incomplete when there is abandoned delivery.
An acknowledged action cannot be abandoned. A conflicting stale action can therefore
be retained while a new explicit attach proceeds; older scope ambiguity remains
visible. No operational approval fences are removed or changed.

## Bounds and acceptance

The spool admits at most256 unresolved requests and10,000 actions, with128KiB bounded
structured input. History-store bounds apply independently. Do not delete pending
records to evade limits; intentional disposition does not remove audit history.
No delivery service, authenticated peer grants, retention/rotation, remote credentials,
shared narrative reader or public UI is supplied by this source slice. Mode/symlink/
sidecar checks protect the normal caller-owned fixture, not a malicious store owner.

Tests use real private client/history SQLite databases and subprocess commands for
multi-request atomicity, lost reply/ack, unavailable store/restart, duplicate/conflict,
concurrent same-action enqueue, explicit session association, stale revision/receipt
refusal, intentional uncertain disposition, private state and immutable requests/
receipts. Existing foundation tests retain their authority and rendering boundaries.
