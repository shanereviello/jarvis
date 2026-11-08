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
leaves active work uncertain and blocks rerun. Automated cross-process runtime
reconciliation is unfinished.

App Server start/resume/turn/cancellation use the supported interface. Permission
or tool requests are never auto-approved; use the existing operator surface.
Desktop conversation injection is not assumed. Managed/interactive worktree
ownership and linked continuation still need acceptance.

## Validation and outstanding acceptance

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
