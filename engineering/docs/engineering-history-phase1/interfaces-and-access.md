# Proposed interfaces, permissions and web boundary

Contract sketch, not live routes or an implemented network/API framework. D1 selects
the storage/writer topology. D2 must select actual authentication/network integration
before any listener is exposed. Do not invent an existing SSO/VPN/reverse proxy.

## Access matrix

| Principal | Curated shared history | Private engineering content | Submit drafts/checkpoints | Root journal / credentials | Execute/merge/deploy |
| --- | --- | --- | --- | --- | --- |
| Human reader | Authorized repositories | Only explicit private-read grant | No by default | No via browser | No |
| Authenticated human operator | Authorized repositories | Own permitted content | Yes, scoped | Existing explicit administrator tooling only | Distinct action decision through later gateway |
| Jarvis client | Published allowlisted documents/views | No | Proposal/agent summary if a separate write credential is granted | No | No |
| Interactive Codex client | Scoped context | Explicit session/repo read grant | Bounded drafts and evidence reports | No new root access | Existing interactive permission policy only; recording token grants none |
| UID996 worker | Exact task material only | No history browsing | Existing bounded worker evidence channel only | Systemd task credential only; no journal access | Exact consumed managed attempt only |
| History service | Own store/content | Own controlled store | Validated intake | No root DB/provider/GitHub credentials | No |
| Protected exporter/control adapter | Allowlisted source facts | Exact selected protected inputs | Signed/transport-bound export receipt, not model-origin truth | Existing protected roles | Existing narrow actions only |

Do not share one read/write/admin token among Jarvis, browser, hook and worker.
Unix-local callers can use peer credentials plus repository policy; remote clients
need authenticated scoped credentials. The browser session principal must not be
claimed by JSON actor fields. A local agent using the same Unix account as its user
is not cryptographic proof that the human clicked an approval.

## Proposed operations

| Operation | Inputs / bindings | Result / constraints |
| --- | --- | --- |
| create work / propose revision | Repository, objective, criteria, scope, source | New draft revision; expected prior head for updates; no execution authority. |
| attach session | Existing work/revision, client/session identity when available | Durable association; explicit active work context. |
| append checkpoint | Client key, expected work revision, structured content/evidence | Idempotent receipt or conflict; body/size bounds; no last-writer-wins scope change. |
| submit document | Canonical structured data, template version, source refs | Private draft version; deterministic renderer; immutable bytes/digest after capture. |
| publish curated document | Exact version/digest, audience, authenticated publication decision | New authorized shared view; no arbitrary private artifact fetching. |
| export operational fact | Source namespace/event ID/digest, bounded allowlisted content | Deduplicated imported source receipt; verify collector identity separately. |
| history/search/read | Authorized repository, cursor/query, audience | Bounded results with version/digest, citations, freshness and supersession. |
| propose action | Action, exact capture/work/doc digests, expected state | Pending decision only. |
| human approve action (later) | Authenticated principal, action-specific target, nonce/expiry/state | Narrow single-use action request; root controls recheck live state. Duplicate/conflicting requests cannot execute twice. |

All writes return durable receipt ID, source/client key and resulting head/state.
Search cursors and document URLs carry no execution grant. Canonical action binding
uses record/document hashes, not mutable 'latest' URLs, title text or UI state.
Model-provided URLs/paths are untrusted references, not fetch instructions. Use exact
repository/commit/PR identities and allowlisted resolvers; no arbitrary SSRF/file reads.

## Web sequence

First read-only: authenticated repository list -> work inbox -> standard review
version -> timeline/checkpoint/completion -> exact allowed evidence links. Display
provenance, imported time versus occurrence time, stale/missing data and whether an
outcome is accepted/merged/deployed/verified. Escape Markdown/HTML, restrict links and
attachments, and avoid running repository scripts to render documentation.

Later controls: present exact action, target version/digest, costs/limits and expiry;
require human authentication/freshness and explicit intent. Protect browser writes
against CSRF, replay and session confusion; actor authorization checked server-side.
Execution/acceptance/merge/deployment are separate buttons/permissions and receipts.
Current GitHub frontend connector is not automatically a server credential; choose
and review the future web merge transport separately. No generic shell endpoint,
unrestricted systemd command, Docker socket or provider credential enters the UI.

## Privacy and retrieval

Default free text stays private until a trusted publication decision. A read-only
root export must explicitly allow newly shared narrative/reference fields; the old
strict projection schema cannot be extended silently. Enforce access before search,
not just when opening a result; snippets can leak text too. Visibility withdrawal
invalidates caches/indexes/cursors appropriately. Show source citations and unknowns;
a generated synthesis never invents rationale or treats an imported deployment as
verified. Initial search can be deterministic metadata/full-text on authorized
curated content; embeddings/remote indexing require a later data-handling decision.
