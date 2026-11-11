# Linear integration: approved v0.4 n8n reuse

Operator-approved architecture SHA-256:
4ed76e0a493a5ae45bcc6154cb57fac3f1551644b1e823d5c96b1e2713365329.
This is source and staged setup documentation, not a completed deployment.

[Step-by-step Cloudflare/n8n setup, matched to the existing installation](cloudflare-n8n-setup.md).

## Responsibilities

Preserve Jarvis's existing app, credential, ingress, restricted Hermes tools and
workflows. n8n owns Codex OAuth and transport. Codex has a distinct generic OAuth2
credential with actor=app and **read write app:mentionable app:assignable** scopes.
The installed built-in Linear credential default omits assignable; actual saved
Jarvis grants were not inspected.

The dedicated Worker verifies Codex HMAC over unchanged bytes, timestamp,
organization and delivery. It forwards to the authenticated Codex-only n8n route.
Use distinct secrets; do not replace the Jarvis Worker. Carry a dedicated Access
service token as CF-Access-Client-Id and CF-Access-Client-Secret headers to the
backend. Add the exact Codex path to the existing tunnel, with scoped Service Auth
protection. Never export secret values.

The private adapter owns only Codex runtime dispatch/result recovery. Shared
ingress/n8n/PostgreSQL outages can affect both agents. Hermes downtime alone does
not prevent Codex. Owned SQLite/private evidence remains engineering authority;
bridge PostgreSQL is transport state, never human agreement or work completion.

## Source package

**linear_setup.py --n8n-redirect-url ... --verified-webhook-url ... --output ...**
renders Codex-only registration. Use the exact displayed n8n OAuth Redirect URL;
the custom /oauth/codex/callback is superseded. Do not recreate Jarvis.

**n8n_codex.py --config ... --output ...** renders four **inactive** workflows:
intake, dispatch, runtime reconciliation, and outbound native activities.
Configuration contains public UUIDs, exact issue/work/design pins, fixed endpoints,
and credential references, never tokens/signing secrets. Actual app/actor IDs must
be bound after installation; fixture IDs are not production defaults. Reconcile
existing imports by reviewed names instead of duplicating them.

**linear-codex-n8n-v1.sql** explicitly adds Codex tables/function in linear_bridge;
no legacy Jarvis table changes. Review schema and file digest before installation.
Repeat migration fails rather than accepting unknown schema. Installation grants
only reviewed transport privileges; source makes no grants. Preserve and compare
legacy rows/DDL before and after.

Intake commits receipt, session and initial thought before acknowledging Linear.
Duplicate source delivery returns the original event. Changed delivery bytes or
source context are refused. Webhook header authentication is mandatory: the
verification header alone is insufficient. Optional app/client payload fields are
checked when present; app-specific signatures, configured ingress and pinned OAuth
viewer identify the recipient.

Runtime dispatch IDs are frozen event UUIDs. The fixed runtime/worktree has one active/uncertain
executor across issues; follow-ups wait. Stop targets the known active turn in that session.
Unknown stop targets remain uncertain. Lost responses require reconciliation,
never another ID and automatic rerun.

Outbound claims a row into **uncertain before sending**, verifies OAuth actor/org,
and publishes the frozen activity UUID. Check GraphQL errors under HTTP 200.
Confirmed unavailable sessions become dead letters; unknown outcomes remain
uncertain, without automatic mutation resend. Initial acknowledgments have
priority. Actual load acceptance must still establish five-second receipt and
ten-second initial-activity timing.

## Private runtime and evidence

**codex_runtime_http.py** provides authenticated POST /v1/dispatch,
GET /v1/runs/<dispatch UUID>, and POST /v1/interrupt. Default bind is loopback;
review private-container networking before deployment. Never expose it through
the public tunnel. Use a separate n8n header credential and owner-only token file.

Installed policy selects binary, cwd, sandbox, app and issue pins. Messages cannot
choose commands or privileges. Real execution must be admitted under the existing
spending/execution authority; architecture approval alone does not grant it.
The journal is runtime evidence, not another OAuth/webhook database. It pins policy,
locks one adapter process, records intent before RPC, and stores thread/lineage/turn
IDs separately. Repeated dispatch returns retained status. Restart or stream loss
leaves active work uncertain and blocks rerun. A status read now uses
`thread/read` for an exact retained thread/turn pair and accepts only a matching
terminal turn with the configured workspace. A missing turn ID, missing history,
different workspace or still-active stored turn remains uncertain. Recovery never
starts/resumes a generation. Full history exceeding the bounded RPC frame also
remains unresolved; paginated-history support is not claimed.

On a normal systemd stop, SIGTERM now unwinds the checkpoint broker and closes
its journal, removing the socket it owns before the next start. A crash or forced
kill can still leave a socket behind; the service refuses to adopt it, and an
operator must confirm it is unbound before removing it. A restart never implies
authorization to repeat an uncertain coding turn.

The runtime event journal retains only lifecycle/approval metadata and visible
agent result messages. Reasoning channels, reasoning items/deltas, unneeded
stream notifications and nested terminal-turn items are excluded before the
bounded queue and again before persistence. Full visible exchanges belong to
the separately selected capture adapters, not this recovery journal.

App Server start/resume/turn/cancellation use the supported interface. Permission
or tool requests are never auto-approved; use the existing operator surface.
Desktop conversation injection is not assumed. Managed/interactive worktree
ownership and linked continuation still need acceptance.

## Validation and outstanding acceptance

### Production observation: human delegation (2026-11-09)

The operator deferred this issue while continuing the remaining work. A direct
human mention on REV-48 reached the Codex runtime and returned the expected
execution-disabled refusal. On REV-49, a human delegation reached the bridge,
but the native origin check returned `origin_unconfirmed` and no coding turn
started. The admitted source-comment ID matches the Linear-generated agent
session thread. That relationship is a lead, not yet a verified root cause:
the individual failing native identity check is not retained in the observation.
Investigate the native session metadata and test a fix without weakening
agent-origin or handoff verification. Delegation acceptance remains open; its
impact may extend beyond REV-49. This observation does not establish a percentage
of functionality complete or verify live model execution or either handoff.

### Delegation origin correction — November 10

A read-only query through the existing Codex OAuth credential showed that the
rejected session's thread is an authorless artificial session root, not an
ordinary source comment. Linear's native response linked that root to the exact
session and identified a human creator matching the signed event's responsible
human. No `sourceComment` or external-source metadata was present. The
[Linear schema](https://raw.githubusercontent.com/linear/linear/refs/heads/master/packages/sdk/src/schema.graphql)
describes the artificial root and distinguishes the session's responsible human
from a source comment; the artificial-root field is marked internal and must be
rechecked for compatibility if Linear changes it.

A source correction accepts this specific shape only when the
authenticated app, workspace, session and issue match; the signed root ID matches
the native artificial root and its reverse session link; the responsible human
matches both the native creator and the independent user read; and there is no
source comment, external-source metadata or correlated handoff. All other agent
comments still require the existing correlated handoff proof. The resulting
observation records the root as the session thread, leaves the triggering actor
unknown, records the responsible human separately, and infers no human approval.
Synthetic unit and n8n engine tests cover
the accepted shape and adversarial mismatches. On November 10 the operator
switched the live dispatch to the corrected inactive-copy candidate. A fresh
human delegation on REV-49 reached the execution-disabled policy and returned
the expected refusal; its retained observation identified the artificial-root
basis, left the triggering actor unknown, and inferred no human approval. This
did not start a model. Live paid execution and the remaining cross-agent
scenarios still require acceptance.

### Live follow-up, cancellation and sandbox diagnosis — November 10

An operator-authorized, isolated, read-only REV-50 test verified a Linear
follow-up in the same agent session and native Codex thread. A separate request
created a separate session and was not counted as continuation. A stop event and
its active turn were both recorded as interrupted. The isolated journal retained
four completed turns and one interrupted turn, and the original execution-disabled
runtime was restored. These tests did not verify cross-agent handoff.

Codex reported that a repository command failed while initializing its sandbox
with a NETLINK_ROUTE socket error. A disposable service confirmed the existing
address-family restriction blocked that socket; permitting AF_NETLINK allowed
it. With AF_NETLINK and the other tested service restrictions, a disposable
service successfully ran a harmless command in the actual Codex read-only
sandbox without starting a model. The operator approved adding AF_NETLINK to
new coding-service sessions. Effective systemd settings were read back with
NoNewPrivileges, empty capability sets, ProtectHome and ProtectSystem preserved.
AF_NETLINK permits the family generally, not only NETLINK_ROUTE. A live coding
turn after this change remains unverified; the result does not establish that
repository access or the rejected escalation path has been repaired.

After that change, a no-model service diagnostic reported read access to the
actual Jarvis README from a read-only Codex sandbox. In a separately authorized
isolated REV-50 turn, the operator requested the README's first three lines and
reported receiving the matching content. The transport and test journal recorded
one completed turn; the owned history contained matching checkpoint, attempt,
session and relationship records. The original execution-disabled runtime was
restored. This verifies the observed read test, not repository writes, the
previous rejected escalation path, or full coding-task acceptance.

### Live Jarvis handoff attempt — November 10

The operator requested a bounded Jarvis-to-Codex handoff on REV-50. Jarvis
reported that the handoff tool was unavailable; no handoff was staged, and
the isolated Codex runtime recorded no turn before the original disabled
runtime was restored. The plugin and toolset are present in the installed
configuration, and normal plugin discovery in a fresh Hermes process registered
`engineering_handoff`. A private, read-only request using the existing n8n
credential found neither the engineering toolset nor its handoff tool in the
running API's toolset inventory. This is consistent with a live discovery or
process-state issue, but does not prove a restart will resolve it. No service
was restarted to reach this conclusion. The diagnostics were imported as
inactive n8n workflows and did not launch models or alter the active workflows.
Both live handoff directions remain unaccepted.

With the operator's approval, Hermes was subsequently restarted after the
recorded Linear-linked runs and handoff queue were idle. The container returned
to running state, but two read-only inventory checks after restart still did
not list the engineering toolset. The restart therefore did not resolve the
observed gap; no new model turn or handoff was initiated. The precise discovery
failure remains under investigation.

Normal discovery under the actual Hermes container identity then identified a
concrete installation defect: the private reporting configuration is owned by
root with mode 0600 inside a root-only directory, so Hermes UID 1000 cannot
read it and plugin loading fails. Its private queue is also owned by root,
although the queue implementation requires the caller's ownership. The queue
was observed empty and healthy. A synthetic, no-network fixture using a
root-controlled group-readable config and a caller-owned private queue
successfully initialized the adapter as Hermes UID 1000. No live permissions
were changed by that fixture. The container identity maps to host UID/GID
1000, also the operator's account, so any production permission change must
account for that shared identity. Live tool registration and handoff acceptance
remain pending.

After operator approval, the installed configuration and scoped bridge token
were made group-readable to Hermes, and the empty private queue was assigned
to the Hermes UID. An audit retained the prior permissions and file digests;
the adapter initialized as Hermes with file bytes preserved. Following an
approved gateway restart, the running API's private inventory reported both
`engineering_checkpoint` and `engineering_handoff` present and enabled. This
establishes live tool registration, not successful handoff delivery; both live
directions still need acceptance.

A subsequently authorized REV-50 Jarvis-to-Codex live test completed: the
transport confirmed the source comment, bound the recipient session, verified
the correlated agent-origin handoff without inferring human approval, and sent
Codex's completed response. Owned history retained requested, acknowledged and
completed handoff records with separate Jarvis and Codex attribution. The
isolated Codex journal recorded one completed turn and the original disabled
runtime was restored. This establishes the tested direction only; the live
Codex-to-Jarvis direction remains to be accepted.

In the first live Codex-to-Jarvis test, Codex reported that its
`engineering_handoff` MCP call was rejected. The test turn completed but no
outgoing handoff was staged; the isolated journal was retained and the original
execution-disabled runtime restored. The installed launcher explicitly sets
approval mode for `engineering_checkpoint` only, while its parent declines
unhandled approval requests. A candidate adds the same explicit setting solely
for `engineering_handoff` when the installed handoff policy enables that tool.
The exact issue/work/session pins, transport checks, recipient, quiescence,
loop limit, human-approval distinction and remaining approval handling are
unchanged. Focused tests and the offline cross-UID App Server fixture pass.
The retained test session confirmed an `mcpServer/elicitation/request` and a
failed handoff call with the reported rejection. The candidate remains
undeployed and live reverse-handoff acceptance remains outstanding.

The first operator-authorized read-only model test did not start: changing the
runtime policy without a matching journal caused startup refusal. The original
disabled runtime was restored. The transport event remains uncertain and was
not retried. Runtime journal inspection found no turn for that dispatch. A
source fix guards terminal bridge states against delayed reconciliation writes;
isolated PostgreSQL and full n8n fixture acceptance passed, but this safeguard
and an audited no-turn reconciliation are not yet deployed. A separate empty
journal with a different policy was also verified in a no-model fixture; it is
not a migration or a production acceptance of live coding.

Focused tests use actual private HTTP, SQLite restart and a synthetic stdio child,
without real models. **probe_n8n_codex.py --isolated-containers** uses installed
images with pull=never, no network/production mounts and disposable PostgreSQL.
It tests real JS admission, generated node compilation, credential refusal,
Worker signatures/unchanged forwarding, SQL replay/conflict and query preparation.
It removes the fixture container and never executes live n8n workflows.

**probe_n8n_engine.py --isolated-containers** adds actual four-workflow creation
and normal-path execution in a disposable n8n 2.28.3 server with a PostgreSQL 18
fixture and synthetic OAuth/runtime endpoints. It tests committed/deduplicated
webhook intake, initial reply, single dispatch, reconciliation and final reply.
Poll triggers are invoked manually and fixture-only execution retention is
enabled for diagnosis; this does not prove production schedule timing, renewal,
cancellation or native messaging. No production mounts or outside connectivity
are available. See [current validation and limits](v04-validation.md).

Before activation, finish:

1. Admin Codex registration and separate n8n OAuth2 configuration; verify complete
   scopes, displayed redirect, returned actor and workspace/team. Keep secrets private.
2. Isolated n8n import/execution, role grants, response handling, concurrency,
   renewal, native handoffs, runtime permissions/streaming/recovery acceptance.
3. Pinned release/runtime packaging, service identity/network/state permissions,
   private credential/encryption-key backup and exact rollback. No secrets in Git.
4. Separate merge/deployment decision on a concrete release. Retain Jarvis workflow
   exports and bridge schema/records first; preserve the repaired database network.
5. Separately authorized real mention/delegation/follow-up/cancellation and both
   handoff directions. Recheck Jarvis without expanding its tools.
6. Remaining SHRR artifact intake, observations/capture, UI, curated retrieval and
   truthful retrospective architecture acceptance.

Old standalone OAuth/inbox/publisher modules remain historical source/test
foundations, **not v0.4 deployment**. The old setup CLI requires
--legacy-standalone. Explicit history recording stays in use until integration
deployment; source instructions do not enable automatic collection.

References: [Linear agents](https://linear.app/developers/agents),
[interaction](https://linear.app/developers/agent-interaction),
[webhooks](https://linear.app/developers/webhooks),
[n8n OAuth](https://docs.n8n.io/integrations/builtin/credentials/linear/),
[Codex App Server](https://learn.chatgpt.com/docs/app-server).
