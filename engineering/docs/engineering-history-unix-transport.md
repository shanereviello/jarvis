# Authenticated local engineering-history transport

This source adds a Linux Unix-stream service around the
[repository access dispatcher](engineering-history-service-access.md). The service
is passive: private engineering intake and scoped reads only. No persistent service,
account, production store, hook, root exporter or browser listener is installed by
this change. Disposable same-UID sockets and processes are used in tests.

## Trust and identity

`tools/rras_history/service_cli.py` opens an existing service-owned private store
and a protected access policy, then listens at one explicit filesystem socket. It
refuses root, worker/control UIDs 996/997 and elevated real/effective UID mismatch.
Clients cannot select a service store or policy through requests. There is no TCP,
HTTP, subprocess action, coding launcher or root journal interface.

On every accepted connection the server obtains Linux `SO_PEERCRED` and looks up
that UID in its fixed repository policy before reading the request. Message JSON
cannot set the authenticated caller. The client verifies the socket owner/mode and
the connected process's kernel UID against its explicitly configured service UID
before sending private content. Receipt v2 separately binds service `writer_uid`
and authenticated `peer_uid`; a UID shared with an agent is not human-click proof.

The runtime directory must already exist, be service-owned and not writable by
group/others. All path ancestors must be canonical directories owned by root or
the expected service UID, with no group/other write access; root-owned sticky
ancestors such as `/tmp` are allowed above the immediate protected parent. Socket
paths are absolute, contain no symlink components and fit Linux's 107-byte payload.
The service creates the socket as mode0660. Directory traversal and socket group
access must be provisioned separately; membership gives a connection opportunity,
not repository permission. The service does not change ownership/group membership.

Policy loading opens a canonical regular file without following a final symlink,
requires one hard link, ownership by root or the service UID, no group/other write
or other access, and a bounded strict JSON payload. Root-owned0640 with an admitted
service group or service-owned0600 is suitable. Parent ownership/write checks also
apply. Policy is fixed for the process lifetime; a reviewed restart loads revocation.
There is no untrusted reload command.

## Protocol and lifecycle

One connection carries one request and one response. Each direction sends a
four-byte unsigned network-order byte count, that many UTF-8 JSON bytes, then a
write-half-close. Trailing/pipelined bytes, truncation, duplicate keys, non-finite
numbers, invalid UTF-8 and excessive nesting refuse. Request frames are at most
256KiB including the RPC wrapper; inner engineering envelopes retain their original
128KiB limit. Response frames are at most2MiB. A history page that exceeds that
bound refuses; retry a read with a smaller limit. Responses contain either the
fixed RPC contract and result or a uniform `refused` error without submitted text,
SQL, policy details or local paths.

Each connection has a five-second monotonic deadline for wire reads/writes,
including partial-frame waits. The server handles one connection at a time with a
bounded listen backlog; it is not a multi-worker or production throughput claim.
SQLite operations retain their existing transaction/lock behavior. A client timeout
can happen after a write committed, so never infer failure means no record exists.
Retry the exact request/key explicitly; the server returns the original receipt.
No transport failure retries coding or performs a compensating delete.

Startup refuses any existing endpoint, including a stale socket, rather than
unlinking it. Normal SIGTERM/SIGINT drains the current bounded wire exchange and
exits; normal cleanup removes only the matching socket inode created by this
instance. A replaced path is preserved. SIGKILL/crash can retain a stale socket;
operators must inspect it and prove no live service owns it before separate cleanup.
Do not automate deletion of arbitrary existing paths to make startup pass.

## Explicit interactive client configuration

The original `--history-store` mode and v1 receipts remain supported for private
local fixtures. A fresh separate client-state directory can instead select a fixed
Unix service endpoint and expected UID:

```sh
python engineering/tools/rras_history/interactive_cli.py init \
  --state /absolute/private/codex-client-state \
  --service-socket /run/rras-engineering-history/service.sock \
  --service-uid DEDICATED_SERVICE_UID
```

These are future installation placeholders, not deployed paths or a runnable
installation instruction. State must already exist as caller-owned0700. Socket
configuration may be recorded while the service is unavailable; queued work stays
pending. The client does not create the service or initialize its store. There is
no fallback from Unix transport to direct database access. Existing client states
retain their fixed transport; no silent migration or queue rewrite occurs.

The selected transport uses `engineering-client.v2` configuration. It accepts only
receipt v2 with the expected service writer, current caller peer, exact request and
work revision hashes, original source provenance, private visibility and no action
authority. A mismatched receipt leaves requests pending and refuses acknowledgment.
Requests acknowledged remotely before a lost response recover by replaying the
same stored request/key. Explicit commands/status remain described in the
[interactive guide](engineering-history-interactive-client.md).

The library `unix.call` also supports the dispatcher's exact repository-scoped
history and document messages. There is no public narrative search/publication or
browser authentication implied by these authorized private reads.

## Acceptance boundary and next work

Tests use real Linux sockets, actual same-UID kernel credentials, disposable SQLite
and real service/client subprocesses. They cover outage/reopen/replay, lost response
after commit, refused caller/routes, private document bytes, frame bounds/deadlines,
unsafe policy/socket paths, receipt mismatches and graceful cleanup. The fixture
service and client run under the current unprivileged account. This is not evidence
of separate-account file denial or cross-UID admission.

Next prepare an immutable payload and isolated host acceptance using distinct UIDs,
a protected policy/store and synthetic records. A human-run sudo procedure must
verify permitted client access, denied worker/store access, actual differing
service/client peer identities, restart/replay, bounds and cleanup. Only then seek a
separate decision for production account/unit/store installation. The existing root
workflow database, Hermes configuration and managed runtime are unchanged. Curated
Jarvis narrative publication, protected operational export, hooks, GUI/web and
human action controls remain later reviewed slices.
