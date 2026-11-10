# Fedora bootc platform

Implementation reference for [ADR-0013](../adr/0013-adopt-fedora-bootc.md).
Replaces the mechanisms in [image-and-updates.md](image-and-updates.md), whose
requirements still apply.

## 1. The model

bootc treats the operating system as an OCI container image that happens to be
bootable.

```
Containerfile  ->  OCI image  ->  registry  ->  bootc upgrade  ->  deployment
                        |
                        +-- install: Fedora netinst + hosted kickstart (ADR-0020)
```

No installer artefact is built by this project at all; the medium is
Fedora's, and it pulls the image from the registry at install time.

Consequences that matter for this project:

- **The build pipeline is a container build.** No custom image-assembly tooling.
- **An update is an image pull**, so it is atomic by construction. There is no
  package-transaction state to corrupt.
- **Rollback is a deployment switch**, not a restore.
- **`/` is read-only.** `/etc` is merged, `/var` persists.
- **The kernel and its modules are one artefact.** This is why the NVIDIA module
  problem disappears instead of being managed.

## 2. Image composition

Base: `quay.io/fedora/fedora-bootc:<release>`, pinned by digest.

| Layer | Contents | Notes |
|-------|----------|-------|
| 1. Base | `fedora-bootc`, kernel, systemd, NetworkManager, SELinux policy | Pinned |
| 2. Graphics | Mesa, NVIDIA driver + module, Vulkan loader | Module built in this layer |
| 3. Session runtime | Wayland libs, PipeWire, portals, fonts, xdg-desktop-portal | Shared by COSMIC and apps |
| 4. Desktop | COSMIC (`cosmic-session`, `cosmic-comp`, greeter) and the assistant as a layer-shell client | ADR-0018 |
| 5. Control plane | `agentd`, `aios` CLI, model store tooling | ADR-0007, ADR-0011 |
| 6. Health | `greenboot` checks, first-boot provisioning | ADR-0013 |

Rules:

- **One desktop, deliberately.** COSMIC is the session (ADR-0018). Plasma and
  GNOME are not installed: a second desktop would double the session surface and
  reopen a UX question this project has already answered.
- **One X server: Xwayland.** X11 applications run through Fedora's
  `xorg-x11-server-Xwayland` inside COSMIC. No standalone X server and no X11
  session ship ([ADR-0019](../adr/0019-no-xlibre.md)). The reason is ABI, not
  taste: third-party drivers, including NVIDIA's, are built against Fedora's
  server ABI, and a fork with its own ABI cannot load them.
- **No compilers or `kernel-devel` in the final image.** If the module is built at
  build time, the toolchain does not ship. This keeps the image small and removes
  an attack surface.
- **No `pip` into the system interpreter.** Workloads use per-app venvs (ADR-0014).
- **Every package justified by a component in the architecture docs.** The image is
  a specification, not a collection.

## 3. Kernel and the NVIDIA module

The critical difference from mutable Fedora: there is no runtime module build.

```
build stage:  install kernel-devel matching the image kernel
              install akmod-nvidia / kmod-nvidia from RPMFusion
              build or install the module against that exact kernel
              strip toolchain, kernel-devel, and build artefacts
final image:  kernel + matching nvidia.ko, nothing else
```

Why this is safe here and fragile elsewhere:

- The kernel cannot change without a new image.
- The module is built against that exact kernel in the same transaction.
- There is no window in which a new kernel is installed and the module has not
  been rebuilt — the classic failure mode that akmods exists to paper over.

**Driver branch pinning.** The driver version is a property of the image. Moving
to a new branch (for a new GPU generation or a security fix) is a release event
with its own test pass, not a routine rebuild.

**If the module fails to load**, the system must still reach a usable desktop with
software rendering. The driver is not on the boot-critical path; a failed module
degrades to `llvmpipe` rather than to a black screen.

## 4. Updates and rollback

```
bootc upgrade      stage a new deployment (pull is the update)
reboot             boot into it
greenboot          run required health checks
                   pass -> mark good, keep previous deployment
                   fail -> count, retry, then roll back automatically
```

**Two corrections to the stock model**, both observed 2026-11-10:

1. **`bootc upgrade` is a no-op for us.** We resolve channels to digests
   (ADR-0015), and bootc documents that with a digest reference every change is a
   `bootc switch`. The update daemon therefore drives `switch`, not `upgrade`.
2. **`bootc-fetch-apply-updates.timer` must be masked.** It ships enabled, runs
   daily, and reboots. Combined with `greenboot` rollback it re-applies the digest
   that was just rolled back from, one to three hours later, producing a boot
   loop. Mask it in the image and let `aios-updated` own the cadence — see
   [ADR-0016](../adr/0016-update-application-policy.md).

**Health checks** live in `/etc/greenboot/check/required.d/`:

| Check | Failure means |
|-------|---------------|
| Compositor reached its ready state | Session is broken |
| `agentd` answered on its socket | Control plane is broken |
| GPU driver loaded and a context can be created | Acceleration is broken |
| Display manager did not crash-loop | Login is unreachable |

`greenboot` handles the boot counter and invokes the rollback. This replaces the
custom A/B counter designed in ADR-0004; the requirement is unchanged, the
mechanism is inherited.

**Never** treat "the update downloaded" as success. The only success signal is a
session that reaches a healthy state and is marked good.

## 5. Secure Boot and MOK

Fedora's shim is signed by Microsoft, so the boot chain verifies. Third-party
kernel modules are outside that chain, which means Machine Owner Key enrolment.

The unavoidable user-visible cost:

1. First boot imports our public MOK certificate (`mokutil --import`).
2. User reboots.
3. Firmware shows the blue MOK management screen.
4. User selects "Enrol MOK", confirms, enters the one-time password, reboots.

This cannot be skipped for NVIDIA on any distribution. Two strategies:

| Strategy | UX | Risk |
|----------|----|------|
| **Build-time key, shipped public cert** | Enrol once, shared by all users | One private key signs every device's module; compromise is fleet-wide |
| **Per-device key at first boot** | Same screens, but key differs per device | No fleet-wide compromise; provisioning complexity |

Recommendation: **build-time key for v1**, with the private key in an HSM or
offline signing environment, and a documented rotation plan. Revisit if the threat
model for the product changes.

The first-run screen must explain this in one sentence. A wiki link is not an
explanation, and this is the step users abandon.

## 6. Storage

| Path | Backing | Notes |
|------|---------|-------|
| `/` | ostree deployment, read-only | Replaced wholesale on update |
| `/etc` | merged, writable | Most config should live elsewhere |
| `/var` | writable | Persists across deployments |
| `/var/lib/aios/models` | writable | Model blobs (ADR-0007) |

**Put `/var` on its own partition.** Models are the largest thing on the device;
separating them means a reinstall or a rollback never risks a 100 GB download, and
resizing is possible without touching the OS.

A dedicated model disk is supported by mounting it at
`/var/lib/aios/models`. Do not invent a second volume-management layer.

Encryption: LUKS on `/var` at install, using the installer's existing support.
`/` need not be encrypted; it contains no secrets.

## 7. Installer and first boot

The install medium is Fedora's own netinst media, driven by a hosted kickstart
that pulls the image from GHCR with Anaconda's `bootc` command (ADR-0020). We
build no installer ISO: the medium is published and mirrored by Fedora, and this
project hosts only the kickstart. Anaconda still handles partitioning,
encryption, and Secure Boot, which satisfies M4 without inventing anything. The
VirtualBox recipe for testing the network install is in
[run/virtualbox.md](../run/virtualbox.md) §7.

First boot, in order:

1. Validate the image signature and refuse to continue otherwise.
2. Import the MOK certificate; explain why in one screen.
3. Offer cloud provider setup, with "skip" as the default.
4. Offer a model download, with a clear size and the option to defer.
5. Reach the shell.

Nothing in that list may require a terminal. A user who cannot complete first boot
alone is not a supported user.

## 8. SELinux

Enforcing, with custom policy for our daemons.

- Start `agentd` and the shell in their own domains.
- Do not ship a permissive exception for convenience; that would undermine the
  argument that owning the compositor improves security.
- Expect this to be the least enjoyable work in the project. Budget for it.
- The tool sandbox (ADR-0008) and SELinux are complementary: namespaces bound
  filesystem access, SELinux bounds what the process may do with what it can see.

## 9. Build, sign, promote

```
commit -> CI build (Containerfile) -> sign image -> push to GHCR by digest
       -> automated install + health test on reference hardware
       -> promote: move a signed pointer in channels/*.json (ADR-0015)
```

No installer artefact is built at any stage (ADR-0020): the install medium is
Fedora's netinst plus a hosted kickstart, and promotion renders one per channel.

- The registry is the update channel. Its availability is a product dependency.
- Image signature verification is mandatory on the device, not advisory.
- Keep the previous N images so rollback targets exist.
- A release is a digest, not a version string. Bug reports name the digest.

## 10. What we deliberately do not do

- Fork Anaconda, systemd, or ostree.
- Fork or patch COSMIC to fit: customisation is configuration (ADR-0018 §4).
- Support BIOS/legacy boot.
- Support `aarch64` in v1.
- Allow runtime package installation outside a documented developer mode.
- Depend on `ublue`/Bazzite images, though we copy their NVIDIA patterns.

## 11. Known risks

| Risk | Effect | Mitigation |
|------|--------|------------|
| Base kernel and RPMFusion module availability diverge | Image build fails, or ships without acceleration | Pin both; build in CI so failure is visible before release |
| bootc interface churn | Build or update scripts break | Pin bootc version; track upstream; keep the Containerfile thin |
| MOK enrolment abandoned by users | No acceleration, confusing experience | One-screen explanation; detect and offer a retry path |
| Image size grows unbounded | Slow updates, large downloads | Layer review each release; measure compressed size |
| Fedora regression | Our release inherits it | Deliberate rebuild cadence, not continuous; test matrix |
| Fedora drops or stops packaging Xwayland | No X11 path in the image; no fallback ships | Track each release; ADR-0019 reopens with the alternatives costed |
| SELinux breaks the shell | Ships broken | Policy tests in CI; permissive only in developer mode |

## 12. Open decisions

- Fedora release to track, and rebuild cadence.
- MOK key custody and rotation.
- Whether `/var` is encrypted by default or offered.
- Registry hosting and signing infrastructure.
- Developer mode: whether a mutable overlay is available at all, and how loudly it
  warns.
- Whether the appliance SKU (ADR-0009) shares this pipeline or has its own.
