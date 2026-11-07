# Two-agent integration foundation and live setup boundary

The approved architecture requires independent **Jarvis** and **Codex** Linear
agents. This source provides private registration-manifest generation, signed
message admission, a durable bounded integration spool, runtime-session binding,
correlated handoff states, frozen activity requests, and an explicit publisher.

`linear_setup.py --public-origin ... --output ...` produces two private OAuth
manifests and prefilled registration URLs. It does not install or authorize them.
The chosen HTTPS origin must actually serve the reviewed callback/event transport
before app installation. Keep that transport separate from the read-only history
dashboard. Do not alter Cloudflare Access or reuse a privileged provider identity
as an incidental setup step.

## Current source behavior

- Both named app configurations are required, with distinct app users, OAuth
  clients, token files and webhook-secret files. Issue/work/architecture bindings
  are explicit and frozen with the spool policy. Policy evolution needs a reviewed
  migration; editing the file does not rewrite old session associations.
- The webhook boundary validates the raw-body signature, bounded JSON and fresh
  body timestamp, organization/app/session/issue identity, and directed event kind.
  It ignores neither signature failures nor scope mismatch. Duplicate delivery
  and source events cannot change their contents or duplicate the stored message.
- Follow-up user prompts keep the same agent/session/work binding. Self/other-agent
  prompt echoes are refused. A source session must be bound before preparing a
  handoff; recipient acceptance binds the recipient runtime to the same issue.
- Frozen reply requests use a UUID-v4 activity ID and exact content. Publication
  checks the app viewer and organization, records an intent before the mutation,
  and retains uncertainty after a lost response. A second publish cannot silently
  resend. A recorded receipt is replayed without another API mutation.
- The HTTP factory accepts only signed POST intake on two named routes. It has
  no history reads, model launcher or OAuth callback yet. `serve-record-only` is
  an explicit development intake mode, not an operational agent deployment.

A received message is **not** an executed run. Handoff `completed` is an exchange
state, not a work outcome. Neither an agent prompt nor a board status is human
architecture approval. The internal publisher is never called by passive intake.

## Before native agent installation / live acceptance

The following remain implementation and setup work, not completed capabilities:

1. Authorized Codex connection to the Reviello Robotics workspace and team lookup;
   real project/issue creation and exact UUID mapping, with replay-safe creation.
2. Two workspace-admin app registrations and OAuth installation with private
   credentials. Implement callback/state binding, token custody/refresh and
   revocation handling before relying on those credentials operationally.
3. Reviewed HTTPS ingress and pinned runtime delivery. Wire the Codex path directly
   to its supported runtime; it must not depend on Hermes. Wire Jarvis to the
   installed Hermes runtime. Preserve existing paid-run and operational authority.
4. Deliver agent acknowledgments/activities within Linear's required time budget,
   then actual directed turns, follow-ups, cancellation and reconnect behavior.
   A `202` intake receipt alone does not satisfy the native agent-session UX.
5. Verify agent-authored mention/delegation handoffs. If native event delivery is
   insufficient, use the reviewed correlated adapter path rather than manual
   operator retransmission or invented compatibility claims.
6. Finish owned-history intake, artifact/mapping contracts, observations, UI and
   curated retrieval, as well as the remaining architecture acceptance scenarios.

Use the current explicit history interface while that integration is unfinished.
No real token, webhook secret or raw payload belongs in Git or chat output.

Primary interfaces: [Linear agent setup](https://linear.app/developers/agents),
[agent interaction](https://linear.app/developers/agent-interaction),
[app manifests](https://linear.app/developers/oauth-app-manifests),
[webhook signatures](https://linear.app/developers/webhooks), and the
[published SDK schema](https://github.com/linear/linear/blob/master/packages/sdk/src/schema.graphql).
