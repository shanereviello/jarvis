# Two-agent integration foundation and live setup boundary

The approved architecture requires independent **Jarvis** and **Codex** Linear
agents. This source provides selected private registration manifests, per-app
PKCE installation custody, signed message admission, a durable integration spool,
runtime-session binding, correlated handoff states, and an explicit publisher.

`linear_setup.py --public-origin ... --agent codex --output ...` produces only the
Codex manifest and registration URL. Without `--agent`, it renders both roles.
An existing active **Jarvis** app actor was found in Reviello Robotics; preserve
that integration and verify its client/capabilities rather than create another
Jarvis. This tool does not register or authorize an app.
The chosen HTTPS origin must actually serve the reviewed callback/event transport
before app installation. Keep that transport separate from the read-only history
dashboard. Do not alter Cloudflare Access or reuse a privileged provider identity
as an incidental setup step.

## Current source behavior

- Both named app configurations are required, with distinct app users, OAuth
  clients, credential locations and webhook-secret files. Issue/work/architecture bindings
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
- The HTTP factory accepts signed POST intake and optionally configured GET OAuth
  callbacks. Neither surface begins installation, renews/revokes credentials,
  launches models or reads history. The callback can be hosted for Codex alone;
  no Jarvis file or service is needed. Development serving binds localhost and
  disables access logging; actual reviewed ingress must also omit callback query
  strings from logs. `serve-record-only` is not a live agent deployment.

A received message is **not** an executed run. Handoff `completed` is an exchange
state, not a work outcome. Neither an agent prompt nor a board status is human
architecture approval. The internal publisher is never called by passive intake.

Installation commands, private configuration and failure recovery are described
in [per-app OAuth custody](linear-oauth-custody.md).

## Before native agent installation / live acceptance

The following remain implementation and setup work, not completed capabilities:

1. Preserve the verified Reviello Robotics project and REV-46–REV-53 mappings;
   finish their additive typed owned-history relationship records. REV-54 is an
   attributed agreement record; setup MCP writes are human-authorized connector
   writes, not native Codex app activity.
2. Workspace-admin registration/installation of the new Codex app and capability
   verification of the existing Jarvis app. The connected MCP surface does not
   expose app registration. Review the tested callback/custody code, then prepare
   the installed service, renewal supervisor and ingress before actual OAuth
   installation. Keep private secrets off chat and out of Git.
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
Token lifecycle and installation behavior:
[Linear OAuth](https://linear.app/developers/oauth-2-0-authentication) and
[app actor authorization](https://linear.app/developers/oauth-actor-authorization).
