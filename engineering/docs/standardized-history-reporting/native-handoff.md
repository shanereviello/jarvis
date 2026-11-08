# Explicit native Linear handoffs

`native_handoff.py`, `linear-native-handoff-v1.sql` and `n8n_handoff.py` implement
an explicit transport path between the separately authenticated Jarvis and Codex
apps. They add no OAuth vault or general workflow engine. n8n retains credentials
and sends each operation under the correct app identity.

The trusted source adapter supplies its actual session, mapped issue, work and
architecture pins, and existing handoff parent. Agent arguments contain a stable
key, summary, requested action, evidence references and limitations. The prepared
intent is redacted and immutable. Neither a handoff nor an app message establishes
human approval or new execution/spending authority. The native runtime's installed
execution policy still applies.

The sender credential creates one frozen context comment after a known terminal
source-runtime observation. The comment escapes executable mention syntax. The
recipient credential then calls `agentSessionCreateOnComment`, creating the
recipient's own native session. A comment has a frozen client UUID; native
session creation has no client session UUID. Each mutation is marked uncertain
**before** the HTTP call. Lost results are reconciled through exact readback of
the source comment, author, issue and recipient session. No uncertain mutation
is automatically resent. Missing/ambiguous readback remains unconfirmed.

Immutable PostgreSQL state evidence records requested, acknowledged and completed
handoffs. Acknowledgment requires an actual recipient runtime binding; native
session creation alone is insufficient. A terminal recipient runtime completes
the handoff transport, without accepting the engineering work. Parent binding
cannot be reset by agent prose. Four successive handoffs in one chain stop further
automatic transfer and require fresh human context. This is a loop circuit breaker,
not per-checkpoint approval. Intents/events are retained; capacity stops new intake
without deleting pending state.

The Codex route now reads the native session and prompt actor through its own
OAuth credential before dispatch. A source comment's actual author is distinct
from Linear's responsible-human field. An agent-authored source comment requires
the exact retained handoff, work pins, recipient identity and source quiescence.
Unknown automation is not converted into a human request. Native origin evidence
is retained separately from runtime results. A source session's new coding turns
wait while its outgoing handoff is active; matching cancellation remains available.

Both SQL files are required before the updated Codex transport can be activated:

- `engineering/contracts/linear-codex-n8n-v1.sql`
- `engineering/contracts/linear-native-handoff-v1.sql`

The handoff renderer produces eight **inactive** workflows: scoped request,
source comment publication, recipient session creation and exact readback for
each direction. Existing Jarvis rows/workflows/grants are not modified by the SQL.
Its legacy session/run columns are read only for explicit native runtime facts;
transport needs no `last_payload`, arbitrary history database or provider access.
Release installation must grant reviewed column/function access, preserve current
Jarvis behavior and reject a credential shared between the two native OAuth actors.

Model-free acceptance passes in actual offline n8n 2.28.3/PostgreSQL 18 containers:
all twelve workflow definitions import, both private handoff request routes work,
both directions publish under the separate source/recipient credentials, an active
source blocks transfer, and lost comment/session responses reconcile without a
second mutation. A correlated native Codex event starts one synthetic dispatch,
with duplicate delivery suppressed. Acknowledgment/completion state evidence and
the existing cancellation, uncertainty, outbox and Jarvis sentinel checks pass.
The fixture's Hermes execution is represented by synthetic bridge rows; it does
not launch a real Jarvis or Codex model. The separate PostgreSQL probe covers
immutable intent, changed replay, changed recipient and parent-reset refusal.

The separate read-only handoff-history endpoint filters by installed organization,
project and issue IDs before returning an advancing, byte-bounded event page. It
exposes no mutation or source-selection argument. `handoff_history.py` freezes each
transition into the private intake queue and delivers ordinary `handoff.record`
versions through the scoped owned-history API. Exact source event digests, native
runtime references and bridge observation times remain attributed. Receipt time
is not substituted for native occurrence time. An unavailable history service
leaves ordered requests pending and never reruns the coding work.

Explicit retained context versions resolve older work/architecture pins during
late import; the current project version is not substituted. Changed source
events, missing initial transitions and unknown context stop collection with a
gap and retained bridge evidence. The actual n8n fixture additionally verifies
the private reader, exclusion of another project's narrative and exact typed
projection. Owned-history fixtures verify all three retained versions, dependency
ordering, outage/replay and historical context preservation.

`engineering_handoff` is an optional tool on the same scoped native MCP server
as the checkpoint recorder. The parent broker supplies the actual active
dispatch/session, mapped work and incoming chain. The coder supplies only bounded
prose, evidence references and a stable key. It receives no n8n token, OAuth
credential or private queue path. The private queue retains immutable requests,
refuses changed replay and stops at capacity without deleting old records.
`runtime_handoff_delivery.py` makes a bounded passive delivery pass to the fixed
Codex admission endpoint. A lost acknowledgment retries that same idempotent
admission, not a Linear mutation or a coding turn. Publication still waits for
source quiescence. A Codex-to-Jarvis request for assistant context does not itself
delegate engineering ownership.

Authenticated n8n origin/binding checks supply incoming handoff metadata to the
coder adapter. It records Jarvis as coordinator only for such an incoming
handoff. Human follow-ups within that same native session preserve the chain;
ordinary prompts cannot reset its depth. Synthetic tests cover wrong recipient,
source identity, session, depth, stale dispatch, replay and admission outage.
The offline cross-UID native App Server probe discovers and calls both tools
through the real MCP path without any model turn or real credentials.

`n8n_jarvis_admission.py` now prepares that bounded patch against an exact private
snapshot of the existing Jarvis workflow. Mapped engineering requests read native
origin through the existing Jarvis OAuth identity, verify the actual comment or
prompt author, and require exact correlated intent for agent-authored handoffs.
The additive admission table retains the result and pins. Unconfirmed requests
record an error without starting an assistant run. Other issues keep the original
run path. All existing run fields, credential references, headers and restrictions
are retained; engineering context adds instructions without repository, terminal,
file or execution access. A flat native `issueId` is normalized as well as
`issue.id`. Changed snapshots or unrecognized topology refuse preparation.

The actual isolated n8n fixture exercises this patch with a synthetic legacy-shaped
workflow and fake Hermes HTTP endpoint: a correlated Codex-to-Jarvis request is
admitted, an agent prompt echo is refused, and an unselected issue preserves its
original request instructions. It caught n8n's restriction on `binding` property
access in expressions; the verified binding is serialized in the Code node before
parameterized SQL. This proves engine behavior, not live Hermes model execution.
The prepared patch has not been imported into or activated on the existing route.

Remaining integration includes Hermes scoped reporting/handoff tools and capture,
deployment packaging and separately authorized
native interaction acceptance. These sources and fixture results do not activate
any production workflow, PostgreSQL migration, collector or runtime. Earlier
private staged transport files must be regenerated from the final source; they
are not the current installation candidate.

The native field/mutation basis is Linear's [SDK GraphQL schema](https://github.com/linear/linear/blob/master/packages/sdk/src/schema.graphql)
and [agent interaction API](https://linear.app/developers/agent-interaction).
Live grant and event behavior still require native acceptance.
