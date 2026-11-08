# Server runtime installation candidate

This is a review candidate for the approved v0.4 build. It does not install or
start anything. The units require an explicit root-owned file at
`/etc/rras-engineering/codex-runtime/host-runtime-enabled`; no such file has
been created by this source work.

## Reuse of the existing engineering API setup

Read-only inspection found the existing engineering key in
`/srv/hermes/data/.env`, under the single variable `OPENAI_API_KEY`. Only the
variable name and file metadata were inspected. The source helper
`prepare_openai_credential.py` reads the existing private dotenv file as root,
requires an owner/mode check and exactly one bounded key, then writes only that
key as a separate root-owned mode-0400 file. It makes no API call, prints no
secret, and never passes the other Hermes environment values to Codex.

The native coding service receives that one file using systemd
`LoadCredential=`. `codex_app_server_entry.py` reads the named credential and
starts the pinned App Server with a clean environment containing only its
`RRAS_OPENAI_API_KEY` and fixed runtime paths. The private adapter and passive
source reader receive no provider credential. To prepare the credential after
the source has been reviewed and installed, the root operator would run:

```bash
sudo /opt/rras-engineering/releases/standardized-history-runtime/venv/bin/python \
  /opt/rras-engineering/releases/standardized-history-runtime/engineering/tools/rras_reporting/prepare_openai_credential.py \
  --source /srv/hermes/data/.env --source-uid 1000 \
  --destination /etc/rras-engineering/codex-runtime/openai-api-key
```

The source path currently belongs to UID 1000 and is mode 0600. The installed
helper refuses any other owner, mode, link count, duplicate key, or unsafe
destination. It writes no credential into the repository or a build artifact.

## Private route and service split

The current n8n container is on Docker network `jarvis-net`, subnet
`172.19.0.0/16`, address `172.19.0.2`, with host gateway `172.19.0.1`. The
candidate adapter binds only `172.19.0.1:8766`; n8n reaches it over that private
bridge. The unit limits its IP traffic to the same subnet. The public Cloudflare
Worker remains the existing verified event-ingress path; it is not used for the
runtime bridge.

The candidate keeps three identities separate:

- `rras-codex-adapter` owns the private HTTP bridge, runtime journal, handoff
  queue and owned-history write client. It has no repository access or provider
  key.
- `rras-codex-native` runs the App Server, receives the one API credential, and
  accesses only the configured worktree and its own Codex state.
- The read-only source App Server runs as `rras-codex-native` without a provider
  credential and exposes only registered source-file reads to the adapter's
  collector client. The adapter client permits only `fs/getMetadata` and
  `fs/readFile` on that connection.

The existing `jarvis-codex-engineering` account is UID 996 and remains reserved
for Jarvis's current role; the new Codex identities must not reuse it. No account,
group, ACL, socket, unit, credential or production history grant was changed.
Socket and timer units are inactive candidates. The private bridge source now
supports resolving the native peer by the installed account name so numeric UIDs
are not guessed in the unit files.

## Acceptance boundary

The source fixtures verify credential filtering with synthetic keys, native
process environment isolation, offline App Server source reads, MCP callbacks,
and n8n engine behavior. `systemd-analyze verify` parses the candidate units on
the server's systemd 249; it reports only expected missing executable paths
because the candidate release is not installed. It also exposed and corrected
the `Accept=yes` service-template naming for systemd 249.

The following still require the merged release and root-owned server setup:

- build the pinned private Python environment and install the immutable release;
- create the two new service users with separate primary groups and no extra
  groups, then create their state/config paths and exact socket ACLs;
- extract the existing API key through the helper and install root-owned runtime
  policy, selected task contracts, capture registrations, n8n bridge token and
  Hermes reader configuration;
- add the adapter UID as the scoped owned-history writer and apply the reviewed
  additive migrations with a consistent database/private-evidence backup;
- run model-free systemd socket, UID, route, outage/restart and refusal checks;
- separately authorize any paid native turn before changing the installed
  execution policy from refusal mode.

The unit candidates do not enable their sockets or timers by themselves. Starting
the runtime also requires the explicit marker file, an initialized journal,
valid task contracts, a valid selected history grant and a complete private
configuration. No real session export or model execution was used to prepare
this package.
