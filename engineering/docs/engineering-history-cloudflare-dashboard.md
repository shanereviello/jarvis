# Cloudflare Access engineering-history dashboard

D2 direction accepted by the operator on November 3, 2026: a server-hosted,
single-operator read-only dashboard, opened from the development machine through
the existing Cloudflare Tunnel + Access pattern used for other web applications.
WARP/VPN remains a separate way to reach SSH. This supersedes the earlier provisional
standalone LAN HTTPS/local-password proposal. It does not authorize deployment.

## User experience

The source interface provides repository-scoped work search/listing, work intent
and scope, acceptance criteria, timelines, exact retained documents and recorded
GitHub evidence links. Reported outcomes remain labelled reported; imported facts
remain imported. Recording/occurrence time and unknown session identity stay distinct.
Criteria are shown as requested outcomes without inferred pass states. Document
Markdown is displayed as text with server and browser digest verification, preserving
source rather than executing embedded HTML or repository code.

The UI uses bundled HTML/CSS/JavaScript only. No external fonts/CDNs, analytics,
embeddings, model calls, edit/approval/execution controls or browser persistence of
history are introduced. Responses are private/no-store. Refusal or service failure
clears private views; leaving/signing out clears them before back/forward restoration.
This cannot revoke material a person already read or deliberately downloaded.

## Source boundaries

`engineering/tools/rras_history_web` contains:

- `access.py`: strict single-operator Access configuration, RS256 signature,
  issuer/audience/email/subject and required time-claim validation. Require exactly
  one assertion header and the configured Host; reject foreign/duplicate Origin,
  alternate key-source headers, duplicate JSON keys, missing/expired/future claims,
  other users, unsigned and symmetric tokens. No cookie/header-only fallback.
- `history.py`: bounded uncached repository-scoped history and exact-document reads
  through an injected existing Unix client. It never opens SQLite or submits notes.
  Receipt associations and exact document manifest/content digests are checked.
- `app.py`: authenticated GET/HEAD-only ASGI routes and security headers. All pages,
  assets and API routes require authentication. Only named assets are served; there
  is no arbitrary file, URL, SQL, shell, export or action endpoint.
- `assets/`: responsive interface using text nodes for history content, same-origin
  requests and safe explicit GitHub links. No automatic server-side evidence fetch.

The factory accepts an explicit `Reader` and `Access` instance; source tests provide
synthetic signing keys and an actual temporary history store/access dispatcher.
There is no production server bootstrap, configuration reader, systemd unit,
packaged release, public preview, service identity or read grant installed by this
source change. Those are the next implementation/host rollout gate. A test callback
is not a production authentication configuration or a native-session observer.

## Token keys and identity

Only a configured `https://TEAM.cloudflareaccess.com/cdn-cgi/access/certs` endpoint
supplies public signing keys. Browser tokens cannot choose its URL. HTTPS uses
certificate verification, no redirects and no inherited proxy configuration. Fetches
are bounded to three seconds/128 KiB; at most 16 distinct RSA public keys of bounded
size are admitted. The key cache expires after five minutes and refresh attempts
are limited to one per 30 seconds. Expiry/rotation/fetch failure refuses access;
there is no indefinite stale-key fallback. No real Cloudflare token or account was
used for source tests.

JWT validation establishes a permitted reader identity. It is not a live recheck of
the Access policy, nor an approval to execute engineering actions. The Cloudflare
Access policy must itself allow only the operator, and origin requests must not
have a bypass route. No future control gateway is implemented here.

Primary references: [Cloudflare private web applications](https://developers.cloudflare.com/cloudflare-one/setup/secure-private-apps/private-web-app/),
[origin token validation](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/validating-json/).
Dashboard dependencies are separate from existing runtime requirements; see
`engineering/requirements-history-web.txt` and its development companion.

## API and scope

| Read route | Result |
| --- | --- |
| `/api/repositories` | Configured repository IDs and verified operator email |
| `/api/works?repository_id=...` | Bounded title/purpose search, pagination and reported outcome labels |
| `/api/works/WORK?repository_id=...` | Work definition, timeline, retained document versions and supported evidence links |
| `/api/documents/DOC?repository_id=...&work_id=...&version=...` | Exact authorized association, Markdown and verified manifest |

Engineering records remain append-only service data. Reads build bounded snapshots
without a persistent private index or cached fallback. A snapshot can lag later
records; it does not revalidate Git, a deployment, native session transitions or
imported claims. Unknown/unauthorized work/documents and service faults return
bounded generic errors without private payloads or paths.

## Production integration still pending

Read-only host discovery found the existing connector as Docker container
`cloudflared` on `jarvis-net`. Its command arguments, environment and credential
files were not read. A host loopback-only listener cannot simply be assumed reachable
from that container; the exact origin route/bind must be rehearsed and selected
before the tunnel changes. The proposal does not silently expose a LAN-wide port,
change Docker networking or recreate the connector.

Deployment must supply the operator-selected public hostname, Cloudflare team
issuer, application audience and permitted email through protected configuration.
No real account identifiers belong in source examples or logs. Use the dedicated
unprivileged dashboard identity (tentative UID 993, availability rechecked), with an
explicit private-read grant for selected repositories and empty write grant in the
existing service policy. Preserve operator, worker and Jarvis roles. The dashboard
must use the existing authenticated Unix transport, not a copied database or UID1000.
Jarvis stays on its separate curated-only reader.

Protected startup/configuration and bounded server settings now have source below.
A following slice must supply the immutable offline package, tested hardened unit,
read-grant/ACL installation and isolated host/connector acceptance. That includes
actual UID/proc/filesystem/network and read/write denial, real Access verification,
service outage/revocation and browser tests. Production grant loading/restart,
listener/tunnel/Access application changes and rollback require a separate explicit
operator deployment decision. Preserve databases, spools, old releases and evidence.

No service, account, credential, Access policy, tunnel or real history permission
has been changed by this source implementation. Backup/restore remains separately
operator-deferred. Lifecycle hooks/scheduling, web writes, remote shell, additional
users and autopilot remain later work.

## Source validation

The focused suite passed 60 tests, using generated signing keys and temporary
history stores. It covers JWT/Host/Origin failures, key refresh boundaries,
repository/document association, receipt integrity, read-only dispatch and generic
service failures. No live Cloudflare account or production history was contacted.

Chromium checks passed for overview, text-only timeline, exact document digest,
search, clearing private views after a service error, and mobile layout without
horizontal overflow. The preview used labelled synthetic data and an injected
fixture token; it does not establish production Cloudflare connectivity. The
loopback fixture was stopped after testing. Browser/runtime libraries were local
workspace QA dependencies, not host or production installations.

## Protected startup source (following PR80)

`rras_history_web/entry.py` now supplies the startup contract. The file passed as
`--config` must be canonical, root-owned, mode 0640, in non-writable root-owned
ancestors, with the dedicated process primary group. It accepts only this exact
field set (example values are synthetic and must not be installed unchanged):

```json
{
  "contract": "engineering-history-web.v1",
  "uid": 993,
  "gid": 993,
  "history_uid": 995,
  "history_socket": "/run/rras-engineering-history/service.sock",
  "repositories": ["jarvis"],
  "issuer": "https://fixture.cloudflareaccess.com",
  "audience": "fixture-audience",
  "email": "owner@example.test",
  "origin": "https://history.example.test",
  "bind": "127.0.0.1",
  "port": 18764
}
```

The startup rejects root, operator, history, curated-reader and worker identities;
requires matching effective/real UID/GID, no extra groups, no capabilities and
`NoNewPrivs`; clears inherited environment and suppresses request/exception logging.
It uses the existing authenticated Unix transport and permits only history/document
calls. Policy grants remain enforced by the history service, not this configuration.

The origin bind is explicit IPv4 loopback or RFC1918, never wildcard/DNS/public.
Accepting an explicit private address does not create routing or authorize exposure.
The connector route, firewall boundary and actual bind still require host rehearsal
and a deployment decision. Uvicorn runs one bounded worker without proxy-header
trust, WebSockets, reload, request logs or environment configuration.

`engineering/config/history-web/rras-engineering-history-web.service.in` is an
uninstalled template. Protected packaging must replace every release/identity token,
verify the immutable dependency payload, and test the actual unit boundaries before
installation. Its Unix socket needs an explicit server-side read grant/ACL; no grant
is created by startup. There is no automatic restart or database recovery path.

The expanded suite passes 92 tests. These verify the startup contract and refusal
cases with synthetic fixtures; they do not prove actual root ownership, cross-UID
transport, the hardened unit, live Cloudflare keys or connector routing. Those remain
required isolated host acceptance. No account, unit or production file is installed.

## Isolated host acceptance package

`host_package.py` builds an exact-commit, hash-verified offline fixture including
separate dashboard dependencies. `stage_host.py` is combined with that same stdlib
verifier into a hash-pinned sudo bootstrap. It refuses existing evidence/release
paths. Staging copies only verified regular payload bytes to a root-owned release;
it never executes the operator-owned candidate in place.

The fixture uses unallocated numeric IDs 61162 (synthetic history) and 61163
(dashboard), refusing occupied NSS IDs, account names or active processes. It creates
two temporary locked no-login/no-home accounts because this host requires NSS
entries for systemd credentials. After units stop and bytes move to root custody,
successful acceptance removes both accounts. Failures preserve evidence and may
retain temporary identities for explicit diagnosis.
Two bounded transient units use a synthetic store under
`/var/lib/rras-history-web-acceptance-attempt02-20261104` and an isolated runtime socket.
The dashboard unit derives its restrictions from the source template, adds a private
network and fixture-private masks, and runs the actual startup and HTTP application.
Generated signing keys replace only the JWKS loader; actual issuer/audience/email,
signature, Host and time validation still execute. Root makes HTTP checks inside
the unit's network namespace. Tokens travel on stdin, not command arguments/logs.

Checks cover process capabilities/groups/environment, protected configuration,
read-only payload/masked private paths, invalid authentication, actual cross-UID
history and document reads, digest verification, repository and write refusal,
source-database preservation, outage and restart revocation without stale reads.
Transient units are stopped on completion/failure; all have a runtime bound. Private
failure evidence is retained and no retry is automatic. No production unit, database,
policy, credential, Cloudflare route or Hermes container is changed.

This fixture does **not** verify live Cloudflare key retrieval, the Docker connector
route, a production service identity or the final packaged production interpreter.
The acceptance release is synthetic test tooling, not a deployment candidate.


The first host attempt passed offline verification but stopped before child execution:
systemd reported `217/USER` for the unallocated numeric identity. Its empty launch
stderr was insufficient; the fixed unit's journal established the cause. Attempt 2
uses new paths/IDs and the temporary account pattern from prior host acceptance.
Original evidence remains retained, and production account design is unchanged.

On November 4, the operator-run attempt 2 returned
`isolated_dashboard_host_verified` for source
`330b7127d68957c5ec5211052cd182add4b3b5a3`, with the 564-file manifest
`fe81ca10d323cbc9aa553f5b87bd8638450249a65e2e09596416c1340cc8efbb`.
It verified all eight listed host cases, unchanged synthetic database bytes,
stopped fixture units and removal of both temporary accounts. A subsequent
read-only check found both units inactive/not-found with PID 0 and no NSS users
for the fixture UIDs. Protected evidence remains under
`/var/lib/rras-history-web-acceptance-attempt02-20261104`.

No production service/history/journal or Cloudflare change was made, and no real
credentials or model API calls were used. Live Cloudflare keys, connector routing
and the final production package remain pending. This source documentation update
does not alter the host-tested runtime bytes.
