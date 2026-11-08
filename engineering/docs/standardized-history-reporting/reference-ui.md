# Reporting reference views

The read-only dashboard retains scope → project → work and the five project
tabs. Overview now shows exact Linear mappings, mapped execution counts,
reported executor/coordinator, latest checkpoint excerpt, retained capture,
handoff and decision counts, and last source states. Last source state is an
observation, not proof that a collector is currently running.

Work cards identify plan/Linear issue and reported agent/result. Architecture
shows decision/deviation observations for the selected exact design version.
Baselines includes reported attempts without treating commits as deployments.
Project History and Work Timeline expose attributed reporting records alongside
the earlier immutable history. Work Evidence opens retained captured exports.
Scope details includes **Unmapped captured evidence** so imports without work
context remain discoverable. Decision observations explicitly distinguish a
recorded statement from authenticated human agreement.

Every reference read uses the view's signed work/project/scope/reporting boundary.
Artifact association corrections affect the effective projection at that
boundary; the original submission and its original context stay unchanged.
Older snapshots do not pick up later corrections or captures. Query filters
accept only exact typed reporting operations and existing architecture versions.

The artifact inspector displays collector/version, source digest/range, capture
time, redaction profile, selected-source reference and coverage limitations.
Preview reads at most four 64 KiB chunks and labels incomplete full-artifact
verification. Download verifies every chunk and the complete SHA-256/length
before creating a file. Chunk reads recheck current authentication and scope;
failed reads, corruption or lost access clear the displayed private data.
Transcript and imported content render as text, never HTML or executable links.
No private transcript is automatically published to Linear or Hermes.

Actual Chromium fixture acceptance verifies project/work navigation, checkpoint
rendering, literal HTML-like source text, exact Unicode export download, corrupt
chunk rejection, private-display clearing and unmapped evidence discovery. The
existing project architecture/diff/closeout/browser failure tests also pass.
These tests use signed synthetic authentication and temporary databases; they
are not an authenticated production browser acceptance or deployment receipt.
