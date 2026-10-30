# Isolated curated writer unit acceptance

This fixture is a synthetic rehearsal, separate from production installation. The
pinned package includes the committed catalog writer, launcher property builder,
fixed probe/controller and offline schema dependencies. The stdlib bootstrap
verifies all package bytes before copying them to a new protected release and
executing the root controller. Existing fixture state is refused; failures retain
private evidence and are not automatically retried.

The root is `/var/lib/rras-curated-writer-acceptance-20261029`, the unit is
`rras-curated-writer-acceptance-20261029.service`, and the service numeric UID/GID
is 61141. The controller refuses existing NSS allocations or active processes
using that identity. No account is created. No production unit is started,
stopped or changed.

The writer unit is derived from the production launcher property builder, with
explicit substitutions for synthetic catalog/working paths, numeric identity,
fixture unit name and probe command. The probe invokes the actual packet writer
API against an empty synthetic catalog. It publishes an explicitly selected empty
preview, verifies the resulting catalog generation and receipt flags, then repeats
the identical packet in a new unit to check receipt replay without a new generation.
It checks actual UID/GID/groups, capability sets, no-new-privileges, private network,
provider-free environment, denial of root-private and same-UID mount-hidden files,
private production history paths and writes outside the catalog. A separate
shortened-runtime unit must stop without reporting success. Only this fixture
unit is stopped in cleanup; its private evidence and release remain.

An empty preview deliberately avoids using real history, private prose or selected
production content. Nonempty preview filtering and withdrawal behavior retain
their existing tests and earlier curated reader host evidence. This fixture does
not invoke the root production launcher, test its real UID-995 CLI, install the
production catalog, test the reader unit, or connect Hermes to a host socket.
Those gates remain explicit. Unit property/syntax and package tests alone are not
host acceptance; only an operator sudo run can establish actual host results.
