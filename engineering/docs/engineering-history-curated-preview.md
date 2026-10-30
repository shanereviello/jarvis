# Private curated retrieval preview foundation

`curated_preview.py` is a passive library for preparing a reviewable candidate for
future Jarvis retrieval. It is not an API route, published catalog, new read grant,
indexing service, installed command or model integration. Existing private history
permissions and the root execution boundary remain unchanged.

`build(rows, selections)` receives explicitly supplied history rows and explicit
curation. Each selection pins a source request digest and provides only summary,
rationale and limitations. The builder validates structured requests and receipt
associations, work/repository consistency, timestamps and bounds. It never copies
source titles, objectives, checkpoint narratives, documents, artifacts or arbitrary
references into the candidate. It does not fetch paths/URLs or infer prose.

The source rows are supplied claims, not authenticated by the library. Output
preserves source provenance and separate recorded/occurred timestamps; unknown
occurrence remains null. Curated prose is labeled agent-reported, source
authentication remains false, and release status stays not-inferred. A selected
source fact or explicit proposed summary is not a human approval, independent
observation or proof of deployment.

The deterministic candidate is `operator_private`, addressed to `jarvis_candidate`
and explicitly `publication_authorized:false`. Even after successful validation,
keep it private. A digest pins reviewed bytes but grants no access. Selection itself
can deliberately contain private text; bounds and field allowlists do not prove
that prose is safe to share. Publication must review the exact selected content.

`search(preview, reviewed_digest, repository_id, query, offset=0, limit=20)` searches
only that exact private candidate with deterministic case-insensitive term matching.
It validates strict entry/header fields, refuses extra payload or promoted authority,
filters by repository before matching and returns pinned citations and bounded
pages. No private source store is queried for snippets or fallback results. Search
on a newly built candidate excluding withdrawn entries yields no withdrawn matches;
this library makes no claim that old snapshots or caches have been revoked.

Bounds: 2MiB serialized input/candidate, 1000 source rows, 100 selected entries,
4096 UTF-8 bytes per curated text field, 256-byte query and 50 results per page.
No remote embedding, telemetry, scheduler, history write or paid model call occurs.

## Following integration gates

The next slice must design/review durable explicit publication and withdrawal,
repository/audience authorization before search, generation/cursor/cache semantics
and safe read-only Jarvis transport. Actual publication needs its own concrete
operator decision. Never give Jarvis private-read permission as a shortcut. Host
mount/peer boundaries need corresponding acceptance before deployment. Browser
access still requires D2 and remains separate. This foundation does not complete
Section5's curated Jarvis retrieval deliverable.
