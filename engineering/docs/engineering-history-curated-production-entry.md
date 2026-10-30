# Curated production read entry and stdio client source

The operator accepted the concrete production topology on October29,2026: a
separate hardened curated read process under existing history UID995, a dedicated
locked reader identity, a separately controlled publication writer, and a read-only
MCP client in Hermes. Private history and catalogs stay outside the container.
This source slice implements read-entry/unit/client behavior only. It does not
provision identities, install a unit, change mounts/configuration or publish data.

## Service entry and unit blueprint

`curated_service_entry.py` scrubs environment, checks the selected service account,
loads protected policy and validates the curated reader dispatcher before changing
endpoint ACLs. Operator UID1000 and the service owner's UID may not be granted on
this container-reachable endpoint: Hermes root can impersonate UIDs. Only dedicated
reader principals with nonempty repository lists get exact named ACLs. Empty policy
can revoke all readers. The callback applies directory/socket ACLs before listen.
No publication/private-history/task-control route is added.

`curated_service_plan.service_unit(release)` emits a fixed protected release unit
blueprint under rras-history with account995. The catalog mount is read-only;
only /run/rras-curated-history is writable. Private history/config/socket, root
journal/task state, credentials, home directories and Docker socket are hidden.
Private network, AF_UNIX-only, empty capabilities, no-new-privileges, system-call
restrictions and bounded stop/resources follow the existing hardened service
pattern. This text/syntax validation is not actual hardened-unit acceptance.

An initialized empty catalog returns a structured empty result with no generation
or publication recorded. An unavailable/refused endpoint still fails; there is no
empty-result fallback for access, transport, corruption or stale-cursor errors.

## Read-only MCP client

`curated_mcp.py` registers only engineering_history_search and
engineering_history_read. Socket and expected service/reader identities are fixed
startup arguments, never model tool inputs. The process requires its actual UID/
effective UID to match the configured reader and refuses identical service/reader
identities. Clearing inherited environment precedes MCP runtime imports. It uses
the connected peer-verified Unix client and never reads a private DB, arbitrary
path/URL or cached generation as fallback. Refusal/unavailability produces a bounded
generic error instructing the caller to discard cached content and search anew.

The client supports the established MCP major1/2 patterns. The pinned Hermes image
uses application interpreter /opt/hermes/.venv/bin/python and MCP2.0.0; system
/usr/bin/python3 is not its application SDK environment. Bundle the existing
reviewed schema dependencies read-only rather than modifying the image or fetching
packages at runtime. The production launch still needs the approved setpriv identity/
group/capability drop before this client starts. The client itself does not elevate,
change UID, request sudo or invoke a provider.

## Validation limits and following work

Source tests exercise empty catalog semantics, broader-principal denial before
ACL/socket work, exact ACL selection, unit constraints/syntax, two-tool mapping,
environment scrubbing, unchanged distinct-identity guard and actual MCP1 stdio
discovery/unavailability. Existing curated/private Unix regressions remain required.
Successful end-to-end read calls with distinct client/service UIDs are a host gate;
there is no testing-only identity bypass in deployed code.

A disposable networkless/capability-free/read-only container using the existing
pinned Hermes image confirmed actual MCP2 discovery and unavailable-source refusal
with offline schema dependencies. It mounted only temporary client code/dependencies,
not production data/configuration/credentials or a host socket. This does not prove
container-to-host peer credentials or unit filesystem isolation. No live Hermes
restart/configuration/image change or paid call occurred.

Next implement the bounded explicit publication control and package these components;
then test the actual hardened unit, distinct reader and Docker/host Unix boundary
with synthetic data, including private-path denial, withdrawal, stale cursor refusal,
restart and ACL revocation. Only after those pass prepare an inactive production
installation and separate activation/content-publication decisions. Browser D2,
automatic session hooks and autopilot remain outside this slice.
