# Reusable historical review export and offline tools package

The root-only `review_export_cli.py` exposes `inspect` and `export` over the
historical custody reader. It selects one exact protected capture, original source
release and original manifest digest. The original release and every file are
verified before loading its document code. Later admission/configuration changes
can revoke execution without making a consistent historical document unreadable.
No command approves execution, contacts history or exports an approval token.

Inspection requires `--approve-private-read` and reports identity/digests only.
Export requires an exact inspected packet digest, a fresh 32-character lowercase
hex export ID and `--approve-private-export`. A changed packet refuses before any
handoff writes. The existing reader remains fixed to recipient UID1000; this does
not introduce arbitrary recipients, root-readable targets or new access grants.
The root original and private operator handoff retain the existing exclusive-write,
fsync and transfer-directory-last behavior. A reused export ID refuses. Preserve
partial evidence and diagnose failures; there is no automatic retry or cleanup.

## Offline package

`review_tools_package.build(source, vendor, destination, commit)` assembles only
fixed committed source files and selected offline vendor bytes. It does not fetch
dependencies, read credentials, inspect production state or install anything. It
rejects an unexpected commit, unsafe paths, symlinks, hardlinks, nonregular inputs,
`.pth`/`.pyc` members, missing core files, changed hashes and bounded-size/count
violations. Verify the output against the returned manifest digest.

This package contains the export and intake commands, their passive dependencies,
schemas and templates. It does not contain captured source configurations, native
worker/control code, test fixtures, runtime records or policy. The historical
reader loads the separately pinned original workflow release for capture custody;
copying native control code into this new package would change its path bindings.

`review_tools_entry.py` uses only the standard library until the externally pinned
manifest and every member have been checked. Root dispatch additionally checks
root ownership and protected ancestors. Only then does it add the verified vendor
path and load the selected command. Use the pinned native interpreter and its
`-I -B` options, never dependencies from the caller's environment.

```sh
# RELEASE is a separately staged protected tools release; HASH is its reviewed digest.
# ORIGINAL is the original protected workflow release; SOURCE_HASH pins that release.
/opt/rras-engineering/releases/native-10/venv/bin/python -I -B "$RELEASE/engineering/tools/rras_history/review_tools_entry.py" --manifest-sha256 "$HASH" export inspect --state /var/lib/rras-coding-control --review-id "$REVIEW_ID" --source-release "$ORIGINAL" --source-manifest-sha256 "$SOURCE_HASH" --approve-private-read
/opt/rras-engineering/releases/native-10/venv/bin/python -I -B "$RELEASE/engineering/tools/rras_history/review_tools_entry.py" --manifest-sha256 "$HASH" export export --state /var/lib/rras-coding-control --review-id "$REVIEW_ID" --source-release "$ORIGINAL" --source-manifest-sha256 "$SOURCE_HASH" --packet-sha256 "$PACKET_HASH" --export-id "$FRESH_EXPORT_ID" --approve-private-export
```

The export mode requires root; the `intake` mode runs as the operator without sudo
and forwards the commands in [the intake runbook](engineering-history-review-document-commands.md).
There is no TCP listener, browser, scheduler, managed task trigger or worker launch.

Building/verifying a package is not installation. A protected staging procedure,
wrapper selection and any production deployment require separate review. This
source change neither installs commands nor modifies existing services. The
existing history service and operational workflow releases remain independent.

The next source bundle additionally supports `events` for the managed-event receiver;
see [managed sync](engineering-history-managed-sync.md). Previously installed immutable
releases retain only the modes included when they were staged.
