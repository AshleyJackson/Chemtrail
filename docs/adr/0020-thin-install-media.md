# ADR-0020: Thin install media, capabilities provisioned after first boot

- **Status:** Accepted (2026-11-11)
- **Date:** 2026-11-10
- **Deciders:** project owner
- **Supersedes:** —
- **Superseded by:** —

## Context

The first installer ISO built from this image is **3,419,379,712 bytes (3.42 GB)**.
The product owner's reaction, in their words, was that the size is "way way too
big" and that "deploying nightlies to github will be super expensive", and that
what they want is "a lightweight netiso, with all items handled post installation
automatically in the background".

That is two requirements, not one, and they have to be answered together:

1. **The install medium must be small** and must not be rebuilt and republished
   every night.
2. **The heavy parts of the system must arrive after install**, automatically,
   without the user driving it.

### What the 3.42 GB is

Measured on the built image and the built ISO, 2026-11-10:

| Part | Size |
|------|------|
| Anaconda installer runtime inside the ISO | ~1.3 GB |
| Container payload inside the ISO (compressed) | ~2.1 GB |
| Platform image, uncompressed, as installed | 6.76 GB |
| `quay.io/fedora/fedora-bootc:45` base, uncompressed | 3.28 GB |

And inside the 3.5 GB the build adds to that base:

| Package group | Bytes | Share of the ISO payload |
|---------------|-------|--------------------------|
| NVIDIA: `xorg-x11-drv-nvidia-cuda-libs` 511 MB, `-libs` 374 MB, `xorg-x11-drv-nvidia` 194 MB, `nvidia-gpu-firmware` 106 MB | ~1.19 GB | the largest single block |
| Graphics: `mesa-vulkan-drivers` 182 MB, `llvm-libs` 153 MB, `mesa-dri-drivers` 56 MB | ~0.39 GB | second largest |

So roughly two thirds of the payload is NVIDIA and graphics, and the rest is the
kernel and a desktop-less base.

### The medium cannot be made small with the current builder

Every installer format `bootc-image-builder` offers, measured 2026-11-10:

| Format | Result |
|--------|--------|
| `anaconda-iso` | builds, 3,419,379,712 bytes |
| `iso` | builds, 3,419,379,712 bytes — byte-identical size, so it also embeds the payload |
| `bootc-installer` | **fails**: `cannot build manifest: failed to run bootc container inspect: exit status 1`, with empty output |

The `bootc-installer` failure is not the image's fault: running
`bootc container inspect` directly in the same image works and returns valid
output (bootc 1.17.1). The builder's own invocation is what fails, and it prints
nothing further even at `--log-level debug`. That format is therefore unusable
today, and the small-ISO path does not exist in this release of the tool.

### Nightly ISOs are impossible, not merely expensive

GitHub release assets are capped at **2 GiB per file**. A 3.42 GB ISO cannot be
uploaded at all. Even a dieted image will not fit inside that cap, and an ISO per
night would be 3 GB of build time and transfer for an artefact almost nobody
downloads: machines on a channel update in place, they do not reinstall.

### The install medium does not have to be ours

Anaconda gained a `bootc` kickstart command (announced 2025-12-31). The
announcement demonstrated Rawhide media only, so before accepting this ADR it was
verified against the release line we track: pykickstart **3.77-1.fc45 from the
Fedora 45 repositories** — the package Anaconda on F45 media uses to parse
kickstarts — registers `bootc` as `pykickstart.commands.bootc.F45_Bootc` and
parses the line below without error, recording it with its options intact
(verified 2026-11-11). In this release the command takes `--stateroot`,
`--source-imgref` (required; a transport prefix such as `registry:` is required),
`--target-imgref` (a transport prefix is forbidden there, and it defaults to the
source value — which is wrong for updates — so set it explicitly) and, new in
F45, `--bootloader` and `--composefs`:

```
bootc --source-imgref=registry:quay.io/fedora/fedora-bootc:rawhide
```

With `inst.ks=` pointing at a file containing that line, Anaconda pulls the image
from a registry over the network and writes it to disk. The installer does not
need the payload on the disc.

This is already proven on our own ISO: the build in
[run/virtualbox.md](../run/virtualbox.md) reached
`Deployment starting: /run/install/repo/container`, which is the same payload
module reading a container. The only difference is where the container comes
from.

The documented limits of that command, as of the same announcement, are: no
support for authenticated registries, no partitioning spanning multiple disks, no
arbitrary mount points, and Fedora installers only for now. None of those block a
public nightly channel on a single-disk machine.

### bootc cannot install packages at runtime

The phrase "items downloaded and tacked on at a later date" has one hard boundary
that the design must respect. Outside a developer-mode image, bootc has no
supported way to install RPMs into a running system. The deployment is the unit.
So a capability added after install is one of exactly three things:

| Mechanism | Applies | Restart needed | Fits what |
|-----------|---------|----------------|-----------|
| `bootc switch` to a derived image | whole OS | yes | drivers, the desktop, anything with a kernel module |
| Container workload | application | no | models, runtimes, tools, services |
| `systemd-sysext` / `confext` | userspace overlay | no (relogin) | add-on binaries that match the base's libraries |

Anything that reaches into the OS itself is an image, and an image arrives by
switching the deployment.

### What genuinely has to be there at boot

The product surface is the assistant, and the assistant is a layer-shell overlay
(ADR-0006) drawn by a compositor (ADR-0018). **A machine with no compositor has no
product.** So the base image must carry COSMIC and the Mesa software path, and
"fetch the desktop later" is not available to us.

NVIDIA is the opposite case. The machine boots without it, runs on `llvmpipe`,
and gains acceleration once the driver layer arrives. That makes it the ideal
deferred capability: it is 1.19 GB of the payload, it is useless to machines
without an NVIDIA device, and its arrival is worth one restart.

## Decision

### 1. Nightlies publish an image, never an installer

`nightly` is an OCI image on GitHub Container Registry, resolved and consumed by
digest as ADR-0015 already specifies. No ISO is built, attached, or stored for a
nightly run. Installer media are produced only for tagged releases, where the
human-facing artefact has a reason to exist.

This alone removes the 2 GiB wall and the per-night cost, and it costs nothing in
engineering: the device fetches only whose layers changed.

### 2. The install medium carries no payload

The installer's job is to partition, fetch the image named in the kickstart, and
hand off. Implementation order:

1. **Now:** Fedora's own netinstall media plus a hosted kickstart containing the
   `bootc --source-imgref=registry:ghcr.io/...` line. We build nothing and host a
   few kilobytes. The medium is Fedora's, published and mirrored by them, so it
   costs this project no storage and no releases.
2. **Then, if the size still matters:** a purpose-built medium that boots a
   minimal environment and runs `bootc install to-disk --source-imgref=...`, with
   a size budget the CI enforces.

The budget for (2) is **512 MiB, measured, not assumed**, and it is not a release
gate until it has been measured once.

### 3. Two images: the assistant, and the driver

- **`aios-base`** — kernel, systemd, networking, podman, COSMIC session and
  compositor, Mesa software rendering, `agentd`, the shell, greenboot. Boots to a
  working assistant on any machine with no GPU driver.
- **`aios-gpu`** — `FROM aios-base` at the exact base digest, adding the NVIDIA
  kernel module and userspace. This is the 1.19 GB that a large fraction of
  machines need and a meaningful fraction do not.

A release is a **pair of digests**, not one. The GPU image is only valid against
the base it was built from, because its kernel module is built against that
base's kernel (the mechanism in `ci/build-nvidia-kmod.sh`). Promotion, signing,
and withdrawal treat the pair as one unit.

### 4. First boot provisions, in the background, once

`aios-provision.service` runs once on first boot:

1. Detect an NVIDIA PCI device (`0x10de` in class space).
2. If absent, do nothing, ever. The device stays on `aios-base`.
3. If present, `bootc switch` to the `aios-gpu` digest that pairs with the running
   base digest, downloading in the background.
4. Let ADR-0016's policy apply the switch: staged now, applied at the next
   restart, with the same safety predicate and the same user choice.

It never prompts, never blocks the session, and reports progress as one line in
the shell. A failed fetch retries on ADR-0016's schedule and never rolls the
device back, because nothing has been applied yet.

### 5. Content is containers, not image layers

Models (ADR-0007), runtimes, and applications are pulled as container images by
the workload layer, on demand and in the background. They do not enter the OS
image and they do not force a restart. Anything that must be inside the OS is a
capability image, per §3.

### 6. Installation requires network, and says so plainly

The installer fails in the first minute with one clear message when it has no
route to the registry, rather than after partitioning the disk. There is no
offline mode in v1; an air-gapped variant is a separate artefact built on request
from a release, not a nightly.

## Consequences

### Positive

- **Nightly distribution cost collapses** from ~3.4 GB per night to layer diffs on
  a registry that is free for public images, and the 2 GiB release-asset cap stops
  mattering entirely.
- **A machine without an NVIDIA device never downloads 1.19 GB** of driver it
  cannot use, and the nightly diffs it receives are smaller because the biggest
  layer is not in its stack.
- **The base image has one job**: boot to a working assistant. That is a much
  smaller surface to test than "everything the product will ever need".
- **The 1.3 GB of Anaconda stops being our artefact.** We ship a kickstart file.
- **Install media become a release event**, which is what they are. Nobody
  re-downloads an OS to update it.

### Negative / costs

- **No offline install in v1.** Air-gapped and lab machines cannot be installed
  from a nightly. This is a real loss and it is accepted rather than solved.
- **The installer is not ours**, so its look is Fedora's Anaconda until the
  purpose-built medium lands. First impressions are Anaconda's.
- **Two images double the release surface.** Build, sign, promote, and withdraw in
  pairs; the base/GPU pairing is now an invariant that CI must enforce, and a
  mismatch means a kernel module for the wrong kernel, which fails to boot.
- **First boot on NVIDIA hardware is software-rendered** until the switch is
  applied and the machine restarts. COSMIC on `llvmpipe` has to be usable enough
  to not look broken, and its performance is now a product concern.
- **The public registry requirement is upstream's constraint, not ours.**
  Authenticated registries are unsupported by Anaconda's `bootc` command today, so
  every nightly channel must be readable anonymously.
- **A failed first-boot fetch leaves a slow machine with no obvious cause**, so the
  shell's one-line status has to be honest about it.

### Neutral / follow-on

- Establishes that a release is a digest pair, which the promotion tooling does not
  yet model.
- The kickstart becomes a reviewed file in the repository rather than an artefact.
- `aios-provision` is a new unit with new failure modes, but it runs once and it
  fails safe: doing nothing leaves a working, if unaccelerated, system.

## Alternatives considered

**Publish the full ISO nightly.** Rejected. It exceeds GitHub's 2 GiB per-asset
cap, so it does not work at any price; and 3.4 GB of build minutes and transfer
per night buys an artefact that channel users never need.

**Wait for `bootc-installer` to work and use that as the only medium.** Rejected as
the primary plan, kept as the preferred end state. It fails today with an error we
cannot fix from here, and a plan whose first step is "an upstream bug is fixed"
has no schedule. If it starts working, it replaces step 1 of §2 and removes
Anaconda from the medium.

**Keep one monolithic image and diet it.** Rejected as the answer to the stated
problem. Trimming `llvm-libs`, Vulkan, and the CUDA libs might save 0.5 to 0.8 GB,
which still leaves a >2 GiB ISO that cannot be published nightly, and it keeps
every device downloading the driver whether or not it has the hardware.

**Defer the desktop instead of the driver.** Rejected. The assistant is a
layer-shell overlay and needs a compositor; a base with no COSMIC is a base with no
product. GPU acceleration is the capability that can genuinely wait.

**Build a tiny installer on Alpine.** Rejected. It introduces a second
distribution to maintain and to test, and the firmware and driver support that make
an installer work on modern hardware is exactly what Alpine's netboot lacks. The
installer is the wrong place to save 300 MB.

**Install RPMs after install, in developer mode.** Rejected. Developer mode
disables the immutability that the whole update model depends on, and shipping a
provisioning step that mutates the deployment breaks the pairing between a digest
and what is on the disk.

## Follow-ups

- Write the kickstart file and decide where `inst.ks=` is served from. The
  medium will be served from the same host as the channel JSON, so this resolves
  with the channel URL question in [docs/README.md](../README.md).
- **Done 2026-11-11:** confirmed that Fedora 45's installer carries the `bootc`
  kickstart command — verified against pykickstart 3.77-1.fc45 from the F45
  repositories, not just the Rawhide demonstration in the announcement; see
  Context for the options this release accepts.
- Measure the actual download of `aios-base` and set an install-size budget; the
  512 MiB medium budget in §2 is a target until it is measured.
- Build `aios-base` and `aios-gpu` from one Containerfile pair, and make CI fail
  when the module's kernel does not match the base's `uname -r`.
- Extend the promotion tooling to carry the digest pair, including withdrawal:
  either digest being withdrawn withdraws the release.
- Implement `aios-provision`, and test both branches: a VM with no GPU (must not
  switch) and one with a passed-through NVIDIA device (must switch and accelerate).
- Measure COSMIC on `llvmpipe` and decide whether first boot needs a lighter
  session while the driver arrives.
- Re-test `bootc-installer` on each `bootc-image-builder` release, and adopt it if
  the `bootc container inspect` failure is fixed.
- Decide the air-gapped artefact: built from a release, or not shipped.
- Update [run/virtualbox.md](../run/virtualbox.md) with the network-install path
  once it has been booted once.
