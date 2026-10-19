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

The original tracked Compose files remain deployment source. The separate
`mcp/compose.release.yml` requires independently selected exact MCP and Linear
images, forbids pulls/builds, preserves existing identities/networks/data mounts,
and references protected `/etc/jarvis/mcp/runtime.env` and
`/etc/jarvis/linear/n8n_bridge_secret`. Missing bind sources cannot be silently
created. Protected config staging, actual image acceptance and rollback are still
required before activation. The maintained `hermes/compose.yaml` removes the four
legacy workspace mounts while retaining assistant data and canonical read-only
repositories. Ledger evidence state paths remain unchanged; its release definition
uses protected secrets and immutable database-script binds.

The MCP Dockerfile pins the existing Python3.11.17 patch release by registry
digest. `mcp/requirements.lock` preserves all32 deployed Linear runtime dependency
versions and permits only the accepted Linux x86_64/CPython3.11 wheel hashes.
No model/runtime feature upgrade is included. Other architectures require their
own reviewed artifact hashes. Ledger relocation uses accepted existing image IDs;
rebuilding its newer canonical application remains a separate compatibility change.

The MCP Dockerfile no longer copies `scripts/`: the maintained source removed
those dated debug helpers, and the application does not import them. This fixes a
clean-source build failure without restoring obsolete helpers.

`mcp/stage_release.py` is the explicit root administrator step after candidate
review. It requires `--candidate` and the exact `--manifest-sha256`, copies verified
source into a fresh `/opt/jarvis/releases/mcp-<commit-prefix>` directory, and copies
the existing MCP environment and bridge credential privately into `/etc/jarvis`.
It changes ownership of **only `/opt/jarvis` itself** to root, preserving its mode
and all original child ownership. Approve that exact parent change before running.
It does not touch `/opt/hermes`; that service has its own later cutover.

Root-private intent/completion and rollback-config copies are retained under
`/var/lib/jarvis-migration`. Config parents are0700; environment files0600; the bridge
file is root:GID1000/0440 for a read-only file bind by the existing runtime group.
No group membership changes occur. Original configuration/secret sources were retained during staging; subsequent
operator-approved retirement is described in the migration status.
The helper never calls Docker/systemd, activates a release or writes a current
symlink. It refuses existing allocations. On any partial failure, preserve the
journal and all paths, do not retry blindly, and inspect before further action.
Disposable-container root tests validate helper behavior; they are not evidence of
host installation, host isolation, service cutover or database recovery.

Host acceptance requirements are service-specific: preserve actual images separately
for MCP and Linear, test disposable protocol/read behavior, stage protected config,
prepare exact rollback and then perform the approved maintenance action. Database
restore verification is required before ledger data/container changes. Packaging
tests do not establish host isolation, live health or successful migration.

For completed host cutovers and remaining retirement/availability gates, see
[migration-status.md](migration-status.md). Historical preparation requirements
above are not instructions to rerun completed maintenance.
