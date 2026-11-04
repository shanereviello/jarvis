# Engineering history implementation status

As-built checkpoint: November 4, 2026. This supplements the accepted
[architecture](engineering-history-phase1/architecture.md) and
[ordered backlog](engineering-history-phase1/backlog-and-acceptance.md). Their
original proposal language records the design baseline. Source merge,
installation, activation, content publication and paid execution remain separate.

The production outcomes below are supported by operator-run deployment and
verification receipts. Those receipts remain in protected host journals; this
page does not reproduce private configurations, source history or credentials.

| Backlog slice | Current position | Remaining work |
| --- | --- | --- |
| 0. Design baseline | Accepted separate unprivileged service/store, preserving root operational authority. | D2 direction accepted: existing Cloudflare Tunnel + Access, one operator; production route/configuration remain pending. |
| 1. Contracts | Structured work/session/checkpoint/document envelopes, deterministic encoding and provenance rules implemented. | Extend additively for reviewed needs. |
| 2. Durable intake/storage | Dedicated private SQLite service deployed with authenticated Unix peers, scoped policy, receipts/outbox and host boundary tests. | Backup/restore verification remains explicitly operator-deferred. |
| 3. Templates/protected binding | Immutable rendering and protected managed review binding deployed. A real review document was exported/imported with exact-byte readback. | Continued workflow coverage; document creation is not mandatory for every legacy capture. |
| 4. Explicit interactive client | Explicit recording client and durable spool implemented; private history service deployed with real explicitly recorded work. | Operator-designated A/B/C continuity verified without replacing the work; native session authentication remains unverified. Convenient integration remains; no universal chat observation. |
| 5. Operational export/retrieval | Event exporter, review-document handoff and repeatable managed-event sync command deployed. Curated reader, restricted writer and Hermes read-only MCP integration deployed; first three selected entries published and read back. | Routine managed lifecycle orchestration and continuing explicit selection/sync coverage. Existing snapshots do not imply automatic freshness. |
| 6. Optional hooks | Not deployed. | Actual client/event acceptance and minimal trusted metadata design after explicit-client integration. |
| 7. Read-only web | First source slice prepared: Cloudflare JWT validation and private work/timeline/document/evidence UI. Not deployed. | Protected startup/configuration, dedicated read-only identity, host acceptance and separately approved Cloudflare/origin installation. |
| 8. Web decisions | Not deployed. | Separate authenticated action bindings after read-only web. |
| 9. Closeout | Individual source/host/deployment checks and operational evidence retained. | Consolidated two-mode acceptance, maintained operator runbook, upgrade/restore coverage and deferred backup work. |

## Installed explicit recording and sync

The private service runs as UID 995. Operator access uses the scoped Unix service,
not direct SQLite access. Work creation, session attachment, checkpoints and
rendering remain explicit; there is no automatic collection of this conversation.

`rras-history-review-export` and `rras-history-review-document` use the protected
passive release `history-review-tools-6e024a608121`. `rras-history-managed-sync`
is separately installed from `history-review-tools-0f9e5e2f3048`, providing explicit
init/inspect/review/apply/resume/status dispatch for managed-event handoffs. The allowlisted
root exporter reads operational source records without writing them. A real managed
task's events and a real protected review document have been imported.

These commands do not start coding or create approvals. A pending capture reports
its frozen source cursor/event count and saved receipt count. A lost response can
leave a committed service record without a local receipt; explicit resume uses the
original event keys and receipt. Finished cursors remain snapshot-specific and do
not establish current source freshness, task success, merge or deployment.

## Curated production retrieval

The protected release `curated-history-4009e5d9e059` contains the dedicated reader
entry, read-only MCP client and one-shot publication tools. The curated reader
service is active and enabled at boot. Its service process uses UID 995, while
only dedicated reader UID 994 has the container-facing repository grant. The
reader serves the curated catalog, with no private-history or action routes.

The installed root-selected writer runs as UID 995 in a restricted transient unit.
Its only persistent writable scope is the curated catalog. Publication binds the
exact request, reviewed preview, client key and expected catalog generation. Root
attempt fences and catalog receipts preserve uncertain outcomes without automatic
retry. A recorded publication flag is not authenticated human identity.

Hermes now preserves its seven existing MCP entries and adds `rras-curated-history`
as its eighth. Its seven existing mounts are preserved, with two read-only mounts
for the immutable curated release and runtime socket directory. The MCP child drops
to UID 994 with supplementary groups and capabilities removed and environment
cleared. The catalog, private history database and private history socket are not
mounted into Hermes. The original container is retained stopped.

On November 2 the operator published three explicitly reviewed summaries:

- The engineering-history foundation's recorded design intent.
- The managed workflow documentation acceptance task's recorded intent.
- The imported journal's merge claim referencing PR #38.

No private document bodies were included. The operator-run completion receipt
reports exact search and readback of all three entries through the configured
Hermes MCP entry, refusal of another repository and the stale empty-generation
cursor, and a stopped writer unit. Publication required no Hermes restart or
configuration change and made no private-history writes or paid model calls.

These entries preserve source receipts, digests, timestamps and provenance.
Recorded intent is not completion; an imported merge claim is not a fresh GitHub
verification or deployment evidence. New history is not automatically published.
Withdrawal creates a new catalog view, and readers must discard stale results.

## Operational evidence and next section

The host retains installation evidence under `/var/lib/rras-curated-installations`,
Hermes integration evidence under `/var/lib/rras-curated-hermes-integrations`, and
publication evidence under `/var/lib/rras-curated-publications`. Preserve these
private records. A failed or ambiguous attempt needs diagnosis before any new
launch, withdrawal or recovery; never restore workflow/history databases merely
to repair a deployment or publication receipt.

Sections 4, 5 and 9 now include the installed operator runbook, explicit managed
refresh review and operator-designated three-session continuity acceptance. The
latter preserves the original work and records; native session authentication is
still unverified. Managed refresh remains explicit rather than automatic.

Current implementation work is Section 7, following the accepted D2 Cloudflare
direction. See the [dashboard source scope](engineering-history-cloudflare-dashboard.md)
for its source checks and remaining host/deployment gates. Lifecycle hooks remain
optional Section 6 work; protected browser actions are Section 8. No production
listener, automatic capture, paid task or autopilot is authorized by this source slice.
