# Existing ledger deployment relocation

`compose.release.yaml` describes relocation of the existing ledger images and data.
The development Compose files remain available for explicit development use.
The release definition requires accepted immutable image IDs, refuses pulls and
bind-path creation, and reuses the existing external volume and networks. It
contains no migration service or application build.

A release is exported from an exact reviewed Git commit using
`deploy/package_release.py --service activity-ledger`, then installed under
`/opt/jarvis-activity/releases/<release-id>`. Init/migration binds resolve within
that immutable release. Existing database files remain on
`jarvis-activity_jarvis_activity_pgdata`; an absent volume is an error, never an
invitation to initialize a new database. Inspect the volume's database marker and
clean-shutdown state before any recreation. Do not run a migration as part of
relocation. Schema migration files in a release are available source, not proof
that a production database has applied them.

Keep application and database version changes separate from path relocation.
In particular, newer canonical adapter source may require database migrations
that an older deployed database has not applied. Accept the existing adapter image
independently and preserve its full image ID for this operation. Do not substitute
a new canonical build without a separate compatibility review and approval.

An administrator copies the five PostgreSQL secret files into
`/etc/jarvis/activity-ledger/postgres/` and the three adapter secret files into
`/etc/jarvis/activity-ledger/adapter/`. Preserve bytes and verify equality privately.
Keep parent directories root-owned and inaccessible to ordinary users. Each file
is root-owned, read-only to its container process group (PostgreSQL's verified
image GID or adapter GID65532), with mode0440. PostgreSQL and adapter have distinct
copies of the app password so each receives only its required group permission.
Do not publish secret values, digests or complete configuration in review output.
Docker bind mounts do not enforce Compose secret uid/gid declarations; set and
check the host file metadata and test access as the actual container identities.

The four adapter evidence mounts retain their existing source paths and write
roles. Do not move or rewrite controller evidence, leases, writer fences or old
worktrees merely to tidy the directory layout. The historical stopped migration
container remains evidence and is not a service to restart.

Before changing any production container, require a current root-private backup
and successful recovery using the same PostgreSQL image in an isolated database.
Record applied schema versions and active lease counts. Preserve the original
containers, images, exact non-secret boundary metadata and private configuration
for rollback. Use exact container IDs for any rename or stop; broad Compose
operations can select both originals and replacements when labels overlap.
Recreating a container cannot roll back schema changes, so none are included.

Restart policy remains `no`, matching the observed deployment. An operator decides
whether the relocated services should remain stopped or become normally running;
do not infer that choice from a successful backup or source merge. Source merge
also does not authorize activation. If normal restart behavior is later chosen,
review and record that policy change explicitly. Readiness requires more than
`pg_isready`: verify actual schema/grants and authenticated adapter reads without
submitting tasks, releasing fences, or initiating paid work.
