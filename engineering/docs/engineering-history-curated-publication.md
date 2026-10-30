# Private local curated publication catalog

`curated_publication.py` adds durable local selection/withdrawal over the private
preview foundation. It is library code, not installed production storage, a history
service route, a published mount or a Jarvis permission. It never opens the private
history database, root journal, credentials or an external endpoint. Caller-owned
fixtures establish local semantics; actual sharing/authentication/host acceptance
remain separate integration work.

## Scope and authority

Initialize a new private directory with a fixed repository allowlist. Only the
unprivileged owning UID can operate it. This owner is trusted, and local config is
not a defense against a malicious process running as that same owner. A future
adapter must bind this policy to real authenticated service permissions and check
access before calling the library. User-supplied JSON is never a principal.

Publication requires an explicit approval boolean, the exact reviewed preview hash,
a client idempotency key and the expected current generation. Every candidate entry
must belong to the pinned repository policy. Local `publication_recorded:true`
means this selection was durably recorded, not that a human was authenticated or
Jarvis access was granted. Receipts explicitly retain `human_authenticated:false`
and `authority_granted:false`; the original candidate's publication authorization
flag remains false. A later authenticated sharing adapter must establish its own
publication decision. Never give Jarvis private-read access as a shortcut.

## Durable generations and replay

Each immutable generation stores the exact request, reviewed preview and receipt
in a private 0600 file. The private 0700 catalog has an atomic `current.json` pointer.
An exclusive process lock protects mutation; writes and directory updates are
fsynced. Only after the new generation and pending pointer are durable does an
atomic rename change the visible head. Readers see an old or new complete view.
There is no mutable per-entry index or background writer.

The expected-head check refuses concurrent stale updates. The same client key and
request returns its original receipt, including after a later withdrawal. It never
moves the head backward on replay. Different bytes with that key conflict. An
operation intent is retained before generation writes. Failure before commit keeps
unreferenced generation/pending/intent evidence; retry refuses rather than silently
adopting or deleting it. A failure after pointer commit can be reconciled through
the existing chain and original receipt. Recovery of uncommitted state requires a
separate reviewed procedure; automatic cleanup/retry is not supplied.

The chain is bounded to128 generations and checked for cycles/digest corruption.
A generation is bounded to2MiB. Historical generations are private diagnostic
material and may include withdrawn text; they are never a reader fallback.
Retention/physical erasure and copies outside this catalog require separate policy.

## Withdrawal and read behavior

Withdrawal selects exact current entry IDs, an expected generation, a fresh client
key and explicit withdrawal approval. It creates a new generation omitting those
entries; unknown IDs refuse. It does not rewrite old source or document evidence.

Search checks repository policy before loading any generation. It searches only
the current curated candidate, never private source prose. Page offsets require a
generation pin; any older generation cursor refuses after publication/withdrawal.
A caller must discard cached results on that refusal. This library does not erase
results already held by an external client or claim deployed cache invalidation.
Empty results after withdrawal reveal no withdrawn snippets through this API.

## Next integration gate

Review a concrete authenticated publication/withdrawal interface, actual writer and
reader principals, repository authorization, transport and cache behavior. Exercise
those real host/client boundaries with harmless fixtures before deployment. Then
obtain separate installation and exact-content publication decisions. No service,
listener, account, shared directory, production content or access grant is created
by merging this source. Browser D2 remains separate.
