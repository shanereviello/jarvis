# Hardened reader and pinned-image host-socket rehearsal

This isolated acceptance connects the actual curated read service entry and stdio
MCP client through a real host Unix socket. It uses a new protected synthetic
state root, a dedicated fixture systemd unit and temporary locked service account
UID/GID 61151. The reader is UID 61152, with a repository-only grant; there is no
service-owner, operator or root grant on the container-reachable socket.

The service command derives the production unit blueprint with explicit fixture
path, runtime-directory, account and unit substitutions. The controller checks
actual process identity, groups, no-new-privileges, capability sets and network
namespace, the read-only catalog mount, and masked same-UID private history and
root/private source paths. No production unit is started or reconfigured.

A disposable container uses the exact already-pinned Hermes image, its existing
application interpreter and SDK, with no network and a read-only root filesystem.
Its only host bind mounts are the immutable synthetic code/dependency release
and the fixture socket directory, both read-only. No database, curated catalog,
private history socket, Hermes data/configuration or credentials are mounted.
Root starts only with the setuid/setgid/setpcap capabilities needed for the tested
`setpriv` drop; the client then requires exact numeric UID/GID, empty groups,
zero capability sets, no-new-privileges, loopback-only networking and a minimal
provider-free environment. No model or provider API is called.

The container exercises real MCP discovery of exactly two tools, successful
repository-scoped search and exact read, cross-repository refusal and denial of
private or action routes. Unknown, coding-worker, operator, service-owner and root
peers are also denied. A synthetic publication is withdrawn between service
runs, after which fresh search is empty and stale search/read requests refuse.
Another restart must preserve withdrawal. Restart with an empty reader policy
must revoke access, including replacement of old named filesystem ACLs.

Only synthetic storage is seeded; private prose exclusion and unchanged synthetic
history bytes are checked. The fixed disposable container name is required absent
before the rehearsal. Failure cleanup stops only a matching pinned-image fixture
container with the exact label and mount sources, and only the fixed fixture unit.
On successful stop, socket removal and root custody precede removal of the exact
temporary service account. Failures preserve state, logs and any temporary
identity for explicit diagnosis; no automatic retry occurs.

The pinned stdlib bootstrap verifies every committed package byte before copying
a protected release and invoking its controller as root. Offline plan/package
tests do not establish host success. Actual operator sudo acceptance is required.
This rehearsal does not install or activate the production curated reader, edit
Hermes configuration, publish real history, invoke the root production writer
launcher/UID-995 CLI or grant execution authority. Those gates remain separate.
