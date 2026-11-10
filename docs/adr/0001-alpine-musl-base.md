# ADR-0001: Adopt Alpine Linux with musl as the base

- **Status:** Superseded by ADR-0009
- **Date:** 2026-11-10
- **Deciders:** project owner
- **Supersedes:** —
- **Superseded by:** ADR-0009

> **Superseded 2026-11-10.** The premises this ADR rests on changed: the shell
> became the product, inference became local-first rather than local-only, and
> distribution became public on unknown hardware. It fails four of the must-haves
> implied by those premises. See
> [ADR-0009](0009-reopen-base-selection.md) and
> [base-selection.md](../architecture/base-selection.md). The reasoning below is
> retained because it is still correct for a known-hardware appliance, which
> remains a candidate SKU.

## Context

The project is an AI-centric desktop operating system. Three properties of the
platform matter more than feature breadth:

1. **Smallest possible trusted base.** The headline feature is executing commands
   a language model produced. A smaller OS means fewer components that can be
   wrong, and a smaller audit surface for the claim "the OS itself was not
   modified."
2. **Fast, deterministic boot.** An assistant that takes 30 seconds to become
   available is a worse assistant, and users will route around it.
3. **Resources belong to the models.** A desktop that idles at 1.8 GiB leaves
   less headroom for weights and KV cache on 16 GiB machines.

Alpine's base image is on the order of 8 MB, boots to userspace in seconds, and
expresses its entire package set in `/etc/apk/world`. OpenRC is a small init
system. `podman` and `crun` are native packages rather than third-party additions.
Alpine is a real operating system, not merely a container base — postmarketOS has
demonstrated that for years.

The cost is musl. It is a substantial cost and it is concentrated in one place:
GPU compute. That is not solved by this ADR, it is accepted by it.

## Decision

Use Alpine Linux as the base, with musl, OpenRC, and apk. Track the current stable
release branch (3.24 at time of writing) and pin every package. Use `edge` only
for components absent from stable, individually and with justification.

Do not fork Alpine. Do not maintain an independent package archive. This project
is a derivative image plus a control plane, not a distribution.

## Consequences

### Positive

- Small, auditable, fast-booting base that is cheap to update as a whole image.
- Declarative package set makes the image reproducible from one text file.
- Native, rootless container runtime with no daemon to secure.
- OpenRC's simplicity is an asset rather than a limitation for an appliance-like
  desktop.
- Strong precedent: postmarketOS, and Alpine's own growing GNOME and Plasma
  packaging.

### Negative / costs

- **No CUDA on the host, and no realistic path to it natively.** Every
  GPU-accelerated PyTorch-class workload must live in a glibc container, which in
  turn requires a working proprietary driver on the host. See ADR-0002.
- A large fraction of the ML ecosystem's published binaries assume glibc. Some
  packages have musllinux wheels, many do not; PyTorch and vLLM do not.
- musl does not implement most locale support. Internationalisation of the desktop
  and of text handling is constrained by upstream work that is still in progress.
- Community-maintained desktops on Alpine move quickly on `edge` and occasionally
  break in ways we did not cause. We inherit that.
- Some third-party applications, particularly proprietary and Electron-adjacent
  ones, will not run. We cannot fix this case by case.

### Neutral / follow-on

- We are now responsible for pinning and testing the desktop stack ourselves,
  because no vendor tests GNOME or Plasma on musl with our kernel and our driver.
- The package set becomes a maintained artefact with its own review process.

## Alternatives considered

**Debian or Ubuntu minimal.** Rejected. Would remove the CUDA problem entirely and
shorten the GPU path by months, but the base is an order of magnitude larger,
systemd is non-optional, and the OS would no longer fit in a 6 GiB verified image
with room to spare. If the Alpine bet later fails on GPU grounds, this is the
fallback — see ADR-0002.

**NixOS.** Rejected. The strongest candidate on pure engineering merit:
declarative, atomic, rollback-native, and excellent at shipping a custom image.
Rejected because it is not Alpine and the project's stated constraint is Alpine,
and because Nix's learning curve is a real cost for contributors. Worth revisiting
if the constraint is ever relaxed.

**Chimera Linux.** Rejected for the base, but its work is load-bearing for
ADR-0002. Chimera is musl with a FreeBSD-style userland and `dinit`, which means
Alpine packages and Alpine documentation do not transfer. We want Alpine's
ecosystem, not just its libc.

**Fedora Atomic / Bazzite model.** Rejected. Solves the immutable-image and
rollback problems well, but inherits a large base, systemd, and Fedora's release
cadence.

**Build a distribution from scratch.** Rejected. The project's differentiator is
the AI layer, not package maintenance. Building a distro consumes the entire
budget before the product exists.

## Follow-ups

- Re-evaluate this decision if ADR-0002 concludes that the proprietary driver
  cannot be maintained on musl. The base decision and the GPU decision are
  coupled, and this ADR is only stable while path A remains viable.
- Track musl locale support; it gates international release.
- Maintain a documented list of applications known not to run, so user
  expectations are set honestly.
