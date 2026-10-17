# Inactive service release preparation

`package_release.py` exports selected tracked source from an exact Git commit into
a fresh directory and records file hashes, modes and the commit in
`release-manifest.json`. It supports `mcp`, `hermes` and `activity-ledger`.
It never builds/pulls images, copies live configuration, installs into `/opt`,
starts containers, contacts models or runs migrations. Use an unprivileged
workspace destination with trusted parent directories.

```sh
python3 deploy/package_release.py --repo . --commit <reviewed-commit> \
  --service mcp --destination /path/to/fresh/mcp-candidate
```

The MCP build context is the candidate root. The ledger build context is
`<candidate>/activity-ledger`, using `adapter/Dockerfile`. Hermes exports deployment
assets only; its current image and private application state are separate.

Selected symlinks/gitlinks and private configuration paths are refused. Worktree
edits and untracked files are never exported. Existing destinations are refused;
on interruption, preserve the partial directory for inspection and use a fresh
destination. Source manifests do not establish image reproducibility: base-image
digests, resolved dependency artifacts and final image IDs must be recorded at
build acceptance. The ledger dependency range remains unpinned and must be
resolved in that slice before claiming a reproducible image.

The tracked Compose files remain deployment source, not ready-to-activate release
definitions. MCP's `.env` reference, Linear's legacy secret bind, Hermes's legacy
mounts and ledger's old state paths still require the reviewed migration changes.
No candidate should be activated directly from this export.

The MCP Dockerfile no longer copies `scripts/`: the maintained source removed
those dated debug helpers, and the application does not import them. This fixes a
clean-source build failure without restoring obsolete helpers.

Remaining host acceptance is service-specific: preserve actual images separately
for MCP and Linear, test disposable protocol/read behavior, stage protected config,
prepare exact rollback and then perform the approved maintenance action. Database
restore verification is required before ledger data/container changes. Packaging
tests do not establish host isolation, live health or successful migration.
