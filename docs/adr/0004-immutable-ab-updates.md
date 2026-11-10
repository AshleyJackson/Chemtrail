# ADR-0004: Immutable image with A/B updates

- **Status:** Superseded by ADR-0013
- **Date:** 2026-11-10
- **Deciders:** project owner
- **Supersedes:** —
- **Superseded by:** ADR-0013

> **Superseded 2026-11-10.** The requirements — atomicity, verifiability,
> automatic rollback — are unchanged and still binding. The mechanism is
> inherited from ostree/bootc generations and `greenboot` rather than built as
> dm-verity plus A/B slots. See
> [ADR-0013](0013-adopt-fedora-bootc.md) and
> [fedora-bootc.md](../architecture/fedora-bootc.md#4-updates-and-rollback).

## Context

A desktop OS that executes model-suggested commands needs a strong answer to
"what changed on this machine, and who changed it". A mutable root with a package
manager provides no such answer: after six months of incremental installs, the
running system is an unreproducible artefact.

Alpine's own update model is `apk upgrade` against a rolling set of packages. It
is fast and it is not atomic. An interrupted upgrade can leave a partially
upgraded system, and there is no supported rollback.

Two properties are wanted:

1. **Atomicity.** An update either fully happens or does not happen.
2. **Reversibility.** A bad update is recoverable without a rescue USB.

## Decision

The OS root is an **immutable squashfs verified by dm-verity, in two A/B slots**,
updated by writing a complete image to the inactive slot.

Specifically:

- Root filesystem is read-only squashfs, verified against a root hash carried in
  the signed Unified Kernel Image's command line.
- Two slots of 6 GiB each. An update writes a whole new image to the inactive
  slot; the running slot is never modified.
- `/etc` is an overlay with a tmpfs upper layer; a small allowlist of paths
  persists via bind mounts from `/var/etc`.
- All mutable state lives on a separate volume: `/var`, `/home`, `/models`. No
  update touches it.
- `apk` is a build-time tool. Runtime package installation is not supported and
  is available only in an explicit developer mode that opens a mutable overlay
  and displays a persistent warning.
- Updates are delta-encoded against the previous release, with a full-image
  fallback.
- A trial-boot counter in an EFI variable triggers automatic rollback after three
  boots that fail to reach a healthy session.

## Consequences

### Positive

- The running system is verifiable: every block of the OS either matches the
  signed hash or the boot fails. This is the property that makes "the OS itself
  was not tampered with" a claim rather than an aspiration.
- Updates cannot brick a device into an unrecoverable state, because the previous
  slot is intact and the counter is independent of disk state.
- Users can roll back without understanding partitions.
- An entire release is one digest, so bug reports can name the exact system.
- Reasoning about the AI layer is simpler: if a persistent malicious change is
  impossible in the OS, the audit surface reduces to user data and models.

### Negative / costs

- **No runtime package installation.** This is the largest UX cost and the
  loudest objection this design will receive. It is a deliberate trade.
- A 6 GiB slot pair costs 12 GiB of disk before user data. On a 256 GB device that
  is tolerable; on a 128 GB device it needs justification, and it is not free.
- Update latency is higher than `apk upgrade`, even with deltas.
- Developer workflow changes: you cannot iterate on a package in place; you rebuild
  an image. This needs tooling that makes a rebuild cheap, or contributors will
  fight it.
- dm-verity on squashfs means no compression-level flexibility and a fixed,
  pre-sized image.
- Secure Boot and verity together require a signed UKI, which brings key
  management into the release process.

### Neutral / follow-on

- Requires a release engineering function: reproducible builds, signing, delta
  generation, and a rollback-tested channel.
- Recovery mode becomes a designed feature rather than "boot a USB": at minimum,
  a way to select a slot and re-run health checks from a shell.

## Alternatives considered

**Mutable root with `apk upgrade`.** Rejected. It is the default Alpine model and
it is genuinely simpler, but it offers neither atomicity nor rollback, and it makes
the system unreproducible over time. For a general-purpose server this trade is
fine; for a desktop that runs model-generated commands it is not.

**Btrfs with snapshots and rollback.** Strong alternative, rejected on
verifiability grounds. Snapshots give reversibility but not *verification*: nothing
proves the running root matches what was built. Also adds a filesystem's failure
modes to the critical path. Worth revisiting if snapshot ergonomics prove more
valuable than cryptographic assurance.

**ostree / rpm-ostree.** Rejected. Excellent model and directly precedent for this
design, but it is a large dependency, tied to its own tooling ecosystem, and
overlaps with what squashfs + dm-verity already provides with far less machinery.

**Single slot with a recovery partition.** Rejected. Recovery partitions are
rarely tested and, in practice, rarely work when needed.

**Stateless / tmpfs root with a read-only base.** Rejected. Attractive for
appliance images, but a desktop has too much legitimate persistent configuration
to make "stateless" honest.

## Follow-ups

- Define the delta format and measure it against a full image on a slow link.
- Specify the health-check contract precisely; a false positive commits a broken
  update, a false negative rolls back a good one.
- Build the recovery shell and test it deliberately by breaking a slot.
- Decide the developer-mode UX, including how loudly it warns.
- Revisit slot sizing after measuring real images; 6 GiB is an estimate, not a
  measurement.
