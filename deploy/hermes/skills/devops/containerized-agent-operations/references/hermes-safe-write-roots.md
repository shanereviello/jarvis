# Hermes Safe Write Roots in Container Deployments

## What the policy does

`HERMES_WRITE_SAFE_ROOT` is an application-level allow-list for generic Hermes file operations. It is separate from Docker mount mode and Unix permissions. When set, the target must resolve beneath one of its entries.

## Correct Compose form on Unix

```yaml
environment:
  HERMES_WRITE_SAFE_ROOT: "/opt/data:/workspace/jarvis-artifacts:/workspace/shared"
```

Each root must correspond to an intentional writable mount. Do not include read-only baselines or evidence mounts.

## Folded-scalar pitfall

Avoid this form for path lists:

```yaml
HERMES_WRITE_SAFE_ROOT: >-
  /opt/data:
  /workspace/jarvis-artifacts
```

YAML folds line breaks into spaces, yielding `/opt/data: /workspace/...`. Hermes splits on `:` and does not trim, so the second entry has a leading space and no longer resolves as the intended absolute path.

## Evidence sequence

1. Inspect the effective environment of the running gateway/service process.
2. Confirm mount source and `rw`/`ro` state.
3. Confirm runtime UID/GID and target parent ownership/mode/ACL.
4. Create a temporary scoped artifact through the actual Hermes file-writing tool.
5. Read it back, then remove only that temporary test file.

A successful `test -w` proves Unix access only; it does not prove Hermes tool-policy access.

## Engineering workspace boundary

Legacy task and baseline mounts are retired from the Hermes deployment. Do not add them back to the write policy or broaden canonical repository permissions. The canonical repository mounts remain read-only. Coding preparation uses the preparation-only stdio integration; execution requires its separate trusted approval and worker path. Private worker state is not mounted into Hermes. Historical task work and runtime evidence remain on the host until their separate retention and consumer audits are complete.
