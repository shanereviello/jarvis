# Protected curated publication launch

`curated_publication_launch.py` is a root-selected one-shot launcher, not an
installer or listener. It requires an exact protected release path and request
SHA-256. Installation must place the launcher and release under protected root
ownership before any administrative invocation; never sudo a caller-writable
source checkout. Root does not import the selected payload.

The request is read only from
`/var/lib/rras-curated-publications/requests/<sha256>.json`. Its complete bytes
must match the supplied digest, fit the 2 MiB bound, and belong to a root-owned
0600 single-link regular file with canonical protected ancestors. The release
and every payload entry must be root-owned without group/other write permission
or symlinks. The existing `rras-history` account and group must map to 995, with
no additional supplementary groups. Neither account nor directories are created.

The fixed `rras-curated-publication.service` transient unit receives request bytes
through stdin, under UID/GID 995. Its systemd properties make the filesystem
read-only except the curated catalog and private temporary scratch space. Private
engineering history, its policy and socket, operational workflow state, provider
credentials, Docker socket, curated reader socket and root publication evidence
are inaccessible. It has a private network, no capabilities, no new privileges,
resource limits, a 60-second runtime limit and control-group termination. An
empty environment is supplied to the worker. The reader MCP has no route to this
launcher. Existing unit-name collisions are refused by systemd rather than
replacing an active job.

Before dispatch, an exclusive protected attempt directory named by the request
digest is created and synced under
`/var/lib/rras-curated-publications/attempts`. A repeated launch with that digest
is refused even if the earlier catalog operation supports receipt replay. Saved
stdout/stderr are private evidence. A successful subprocess return is reported as
`writer_returned`, with `publication_verified: false`; this launcher does not
infer a valid catalog receipt or content delivery. Timeouts, transport errors and
nonzero exits preserve evidence and do not automatically stop, retry, roll back
or adopt catalog intents. Systemd enforces its independent runtime limit.

Focused tests verify fixed sandbox properties, unit syntax, exact selectors,
ordinary-user refusal, attempt exclusion and timeout preservation without
starting systemd. These are not actual sandbox acceptance. Before installation,
the next isolated host fixture must verify the real write/private-file/identity
boundaries, fixed unit exclusion, timeout/stop behavior, and catalog readback.
The hardened reader and pinned Hermes-image host-socket acceptance also remain
pending. No production content, account, unit or configuration is changed by
merging this source.
