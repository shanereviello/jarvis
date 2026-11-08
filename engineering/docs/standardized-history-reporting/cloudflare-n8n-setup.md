# Codex + Linear + n8n: setup guide matched to your Cloudflare screenshots

Date: November 7, 2026, America/New_York
Architecture: approved v0.4. This guide clarifies installation; it does not change
the architecture or authorize deployment.

## What is reused, and what is added?

**Yes, Codex gets a separate Cloudflare Worker. We reuse the existing n8n
installation, PostgreSQL service, and server01-rack tunnel.**

| Component shown or planned | Treatment |
| --- | --- |
| Existing Worker: linear-agent-ingest | Keep as Jarvis's Worker. Do not replace its code or secret values. |
| Existing tunnel: server01-rack | Reuse. No second tunnel or connector installation. |
| Existing n8n editor route | Reuse for administration and the OAuth callback. |
| Existing hooks route for /webhook/linear-agent-events | Keep for Jarvis. It does not match the new Codex path. |
| Existing history dashboard and private CIDR route | Keep unchanged. |
| New Worker: linear-codex-ingest | Add for Codex signature checks and forwarding. |
| New Worker custom domain | jarvis-agents.reviellorobotics.com |
| New backend path on the existing hooks hostname/tunnel | /webhook/rras-codex-agent-events → http://n8n:5678 |
| New native Linear app and n8n OAuth credential | Codex only, separate from Jarvis. |
| New n8n workflows and private runtime adapter | Source exists; installation/activation is not complete. |

Reusing infrastructure does not mean forwarding Codex requests through Hermes.
Each app keeps its own identity, signing secret, routes, runtime and replies.

## Follow the two different paths

Incoming work:

Linear Codex app
→ https://jarvis-agents.reviellorobotics.com/webhooks/codex
→ new Codex Worker verifies Linear signature
→ https://hooks.reviellorobotics.com/webhook/rras-codex-agent-events
→ Cloudflare Access service authentication
→ existing server01-rack tunnel
→ http://n8n:5678/webhook/rras-codex-agent-events
→ Codex n8n route
→ private Codex runtime adapter.

OAuth authorization:

Your browser → Linear authorization → existing n8n OAuth callback:
https://n8n.reviellorobotics.com/rest/oauth2-credential/callback

The Worker does not handle OAuth or store Linear access/refresh tokens. The
runtime adapter is private and gets no public tunnel route.

The public Worker hostname and the backend hooks hostname serve different roles.
Do not add jarvis-agents.reviellorobotics.com as an n8n tunnel hostname; it belongs
to the Worker.

## Stage 1 — the action requested now: register Codex in Linear

You can reserve the app and its addresses before the Worker exists. Registration
is different from installing/authorizing the app.

1. Open https://linear.app/settings/api/applications/new.
2. Create a private app named **Codex**.
3. Enable authorization-code grant.
4. Set callback: https://n8n.reviellorobotics.com/rest/oauth2-credential/callback.
5. Set webhook: https://jarvis-agents.reviellorobotics.com/webhooks/codex.
6. Select AgentSessionEvent / Agent session events.
7. Save the generated client secret and webhook signing secret privately.
8. Send only the public Client ID. Leave the Jarvis app untouched.

**Do not install/authorize Codex yet.** The new ingress and workflows are not live.
If Linear insists on a working webhook during registration, leave that portion
pending; report the validation message without secrets, and we will stage ingress
first. Do not point Codex at the existing Jarvis webhook to satisfy validation.

## Stage 2 — prepare the Codex credential in the existing n8n

This is a separate credential inside your existing n8n; no new n8n server.

Choose **OAuth2 API** (generic OAuth2) and name it **Codex Linear**. The installed
Linear-specific credential defaults do not request both agent permissions.

| Field | Value |
| --- | --- |
| Grant type | Authorization Code |
| Authorization URL | https://linear.app/oauth/authorize |
| Access Token URL | https://api.linear.app/oauth/token |
| Client ID | New Codex app's public ID |
| Client Secret | New Codex app's secret, entered privately |
| Scope | read write app:mentionable app:assignable |
| Auth URI Query Parameters | actor=app |
| Client Authentication | Body |

Confirm that the credential editor's displayed OAuth Redirect URL exactly matches
Stage 1. If it differs, use the displayed value and reconcile the app callback.
Save configuration without clicking Connect / Sign in until the installation step.
Actual credential fields and refresh behavior remain part of acceptance.

Mentions and delegation are both required. Neither permission creates an extra
approval queue. No Jarvis token or credential should be copied into Codex.

## Stage 3 — prepare the backend tunnel route and Access protection

These are deployment steps for the reviewed release, not changes required merely
to register the app. Your screenshots do not show existing Access application
policies; their hostname/path coverage must be checked before saving a new route.

On the tunnel page shown in screenshot 2:

1. Open Networking → Tunnels → server01-rack → Routes.
2. Add a **Published application** entry for:
   - Subdomain: hooks
   - Domain: reviellorobotics.com
   - Path pattern: ^/webhook/rras-codex-agent-events$
   - Service: HTTP, n8n:5678 (displayed as http://n8n:5678).
3. Preserve the existing Jarvis path, editor route, history route and private CIDR.
   Ensure the Codex path is not shadowed by a broader matching route.
4. If the UI refuses another path on the same hostname, do not delete its DNS
   record or replace the Jarvis entry. Reconcile the exact current route first.

The path is a matcher, not a rewrite. The n8n webhook node must use path
rras-codex-agent-events, giving production URL /webhook/rras-codex-agent-events.
Do not put the full webhook path into the Service URL. The temporary n8n
/webhook-test/ URL is not the production target.

Create a separate Access service token named **Codex Linear Bridge**, admitted by
a **Service Auth** policy for the exact backend host/path:
hooks.reviellorobotics.com/webhook/rras-codex-agent-events.

Retain existing Jarvis Access policies. Verify any existing broader application
and path precedence before adding this policy. This guide does not assume that
the old token is authorized for the new path.

The Worker sends CF-Access-Client-Id and CF-Access-Client-Secret when contacting
the backend. These are service credentials, not your account email or a general
Cloudflare API token. Save the new values privately. n8n also verifies its own
distinct header credential, so Cloudflare Access is not the only check.

## Stage 4 — create the new Worker and connect its public hostname

Do this with the reviewed corrected Worker source, not a generic proxy template
or the current Jarvis code. The draft source now includes the Access headers
identified in your screenshot.

1. In Workers & Pages, create a Worker named **linear-codex-ingest**.
2. Use the reviewed codex_edge_worker.mjs source from this project's release.
3. On the new Worker's Domains/Domains & Routes tab, add Custom Domain:
   jarvis-agents.reviellorobotics.com.
4. Cloudflare creates the Worker DNS/certificate binding. If the hostname already
   has a record or service, reconcile that conflict rather than overwriting it.
5. Under Settings → Variables and secrets, configure the following on the new
   Worker only:

| Type | Variable name | Where its value comes from |
| --- | --- | --- |
| Secret | CODEX_WEBHOOK_SECRET | New Codex app's Linear webhook signing secret. |
| Secret | CODEX_N8N_BRIDGE_SECRET | Newly generated private bridge secret, also entered in the matching n8n Header Auth credential. |
| Secret | CF_ACCESS_CLIENT_ID | New Codex Linear Bridge Access service token's client ID. |
| Secret | CF_ACCESS_CLIENT_SECRET | Same new Access service token's client secret. |
| Text | CODEX_N8N_URL | https://hooks.reviellorobotics.com/webhook/rras-codex-agent-events |
| Text | CODEX_ORGANIZATION_ID | Reviello Robotics organization UUID: 49caeb3f-bbf7-429d-83f6-7ab4de8c8bba |

A bridge secret can be generated privately on a terminal with: openssl rand -hex 32.
Store its output privately; do not paste it in chat. This is separate from both the
Linear signing secret and the Cloudflare Access service token.

The new n8n Header Auth credential must match:
header name X-RRAS-Codex-Bridge, header value CODEX_N8N_BRIDGE_SECRET's value.
Use a separate credential for n8n → runtime authentication.

The public Worker accepts signed Linear requests. It cannot require interactive
browser login from Linear. Service Auth protects its backend hooks path. Do not
remove the existing n8n editor login or alter its policies.

## Stage 5 — workflow/runtime installation, then app authorization

I prepare and test the workflow imports, transport-table migration, private
runtime configuration, release and verification commands. Do not independently
rebuild these in the live n8n UI from a diagram.

The staged release must establish the actual OAuth actor/org, production webhook,
fixed issue/work/design pins, separate credential references and runtime authority.
Keep dispatch disabled while binding identity. At the appropriate installation
step, you complete n8n's Connect/Sign in flow as workspace admin, explicitly
installing the Codex app with both permissions. Bind the returned Codex actor ID
before enabling processing. It is different from the Client ID.

Verify raw signature and invalid-request denial, Access/header denial, durable
receipt-before-ack, native initial reply, mention, delegation, follow-up, stop,
both handoff directions and Jarvis regression. Real model runs retain their
existing separate authorization. Registration alone does not permit them.

## What is ready, and what is still pending?

Source exists for the Worker, inactive n8n workflows, transport SQL and private
runtime adapter. The corrected Worker passes a model-free fixture proving both
Access headers are forwarded and missing Access configuration is refused.
That fixture does not test your actual Access policy or tunnel.

Native app installation, actual n8n workflow execution/import acceptance, runtime
recovery/handoffs, release deployment and the remaining SHRR capabilities are
unfinished. This guide is a map of the complete setup; only Stage 1 is requested
from you now.

No live Worker, DNS, Access, tunnel, n8n workflow or credential was modified while
preparing this guide. Source is on the existing draft PR. The repository's
AGENTS.md says: “Merge and deployment require a separate explicit human decision.”
The later deployment stages are documented here so you can see them in advance;
they are not silently activated by app registration.

## References

- [Worker custom domains](https://developers.cloudflare.com/workers/configuration/routing/custom-domains/)
- [Tunnel path routing](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/get-started/create-remote-tunnel/)
- [Access service tokens](https://developers.cloudflare.com/cloudflare-one/access-controls/service-credentials/service-tokens/)
- [n8n Linear credentials and redirect](https://docs.n8n.io/integrations/builtin/credentials/linear/)
