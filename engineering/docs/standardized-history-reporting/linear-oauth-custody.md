> **Superseded for deployment by approved v0.4.** n8n now owns OAuth. This
> document describes historical source only; follow [the current integration
> runbook](linear-integration.md) and do not install this standalone service.

# Private per-app installation custody

This is source/fixture acceptance, not a deployed native agent. Each role has a
separate caller-owned 0700 vault and 0600 SQLite database. Its frozen policy pins
the role, public origin, OAuth client and organization, and excludes the other
app and human actors. A new actor is discovered only after PKCE exchange and an
authenticated query proves an active app in the expected organization. Save that
verified actor in the inbox policy before admitting messages. Callback completion
does not edit an existing inbox policy or enable runtime execution.

New Codex installation configuration (placeholders are intentionally invalid):

```json
{
  "contract": "linear-agent-oauth.v1",
  "agent": "codex",
  "organization_id": "49caeb3f-bbf7-429d-83f6-7ab4de8c8bba",
  "oauth_client_id": "<actual Codex app client UUID>",
  "public_origin": "<reviewed deployed HTTPS origin>",
  "expected_actor_id": null,
  "excluded_actor_ids": [
    "18e4b8f5-92bc-472c-bee8-2846b156f6e9",
    "ab1d826e-af22-4d0c-bef3-16fa5aad1ed2"
  ]
}
```

Keep actual configuration and state outside Git. The client UUID is public; the
webhook signing secret and tokens are private. PKCE does not require copying a
client secret into this implementation. The flow never requests an installation
scope update or switches to a client-credentials grant. Preserve the existing
Jarvis authorization; replacing it requires coordinated installation work.

Use the selected release's Python with `linear_oauth_entry.py`:

1. `init --configuration /private/codex.json --state /private/codex-oauth` creates
   custody without contacting Linear.
2. After callback deployment and transport checks, `begin` with those arguments
   and `--authorization-file /private/codex-installation.json` saves a one-time
   operator URL privately. It requests `actor=app` and S256 PKCE; state expires
   after ten minutes. Terminal output contains only the file location and expiry.
   Keep the URL, callback code and tokens off Git, chat, issues and access logs.
3. Callback consumes state before exchanging the code and retains the pair before
   identity validation. Completed replay never exchanges twice. A process lock
   prevents overlapping exchanges/refreshes. Wrong actor/scope/workspace leaves
   credentials quarantined and unavailable for publication.
4. `status` is sanitized. `refresh` explicitly renews and saves the pair atomically.
   Reported `expires_in` determines expiry; callers refuse tokens within sixty
   seconds of expiry. A continuous renewal supervisor is **not yet implemented**.
5. `reconcile-identity` retries only identity verification of a retained pair,
   keeping its original expiry. An uncertain code exchange is never replayed;
   reconcile in Linear before replacing custody. For a lost refresh response,
   `recover-refresh` explicitly reuses the retained refresh token within a
   conservative 29-minute window. No automatic retry or reinstall occurs.
6. `revoke` blocks local use before contacting the fixed Linear endpoint. Failed
   or uncertain revocation remains blocked with custody retained. Reconcile a
   lost refresh response first because the historical token may be obsolete.

Revocation removes the usable pair from the current record; it does not promise
secure erasure of SQLite pages or backups. Protect the whole vault as credentials.

`linear_agent_entry.py publish --policy ... --state ... --agent codex --key ...
--oauth-configuration ... --oauth-state ...` publishes only a previously frozen
activity. It checks role/client/organization against the inbox and uses the
pinned actor. A 401 blocks that credential generation without renewal or replay
of a potentially uncertain mutation. Custody exports no loose access-token file.
The inbox policy's older token-file references remain reserved for independently
managed installations; this publisher does not read or overwrite them.

`serve-callback-only` is an explicit localhost development mode. The combined HTTP
factory can serve configured callbacks and signed inboxes. There is no public
installation-start, token, refresh, revocation or status endpoint. Disable query
logging at every actual proxy/ingress before installation. Neither HTTP route
nor publisher launches models or grants execution authority.

Primary interfaces: [Linear OAuth](https://linear.app/developers/oauth-2-0-authentication),
[app actor authorization](https://linear.app/developers/oauth-actor-authorization),
and the [published schema](https://github.com/linear/linear/blob/master/packages/sdk/src/schema.graphql).
