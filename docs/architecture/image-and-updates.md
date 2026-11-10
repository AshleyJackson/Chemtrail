# Image, boot, and updates

> **Superseded mechanism (2026-11-10).** The base is Fedora bootc, so the
> mechanism described here — dm-verity plus A/B slots — is not what we build.
> ostree/bootc generations and `greenboot` provide the same properties. See
> [fedora-bootc.md](fedora-bootc.md). This document is retained for the
> requirements it states: atomicity, fail-closed verification, automatic
> rollback, and an untouched state volume.

## Design stance

The running system is read-only and hash-verified. Anything writable is
explicitly accounted for. This is what makes it acceptable to build an OS whose
main feature is running commands an LLM produced: if the OS image cannot be
modified in place, a bad instruction cannot persist by editing the OS.

Package installation at runtime is not a supported workflow. `apk` exists on the
image, and a developer mode can open a mutable overlay, but doing so is a
documented escape from the model, not the default.

## Partition layout

| Partition | Size | Filesystem | Purpose |
|-----------|------|------------|---------|
| ESP | 1 GiB | FAT32 | UKI for slot A and slot B, boot counter |
| Slot A | 6 GiB | squashfs + dm-verity | OS image A |
| Slot B | 6 GiB | squashfs + dm-verity | OS image B |
| State | remainder | ext4 or btrfs | `/var`, `/home`, `/models` |

Two 6 GiB slots rather than a shared mutable root: an update writes a *complete*
new image to the inactive slot, so there is no partial-update state to recover
from. If the write fails, the device still boots the slot it is running.

The state volume is never touched by an update. This is the rule that makes
updates safe: an update can fail freely, because it cannot damage user data.

Optional LUKS2 on the state volume, unlocked by TPM2 with a recovery key. The OS
slots stay unencrypted deliberately — they contain no secrets and encryption
would break dm-verity simplicity.

## Boot chain

1. UEFI firmware verifies the UKI signature. With Secure Boot on, this is the
   firmware's own trust store; otherwise it is advisory only.
2. The UKI bundles kernel, initramfs, and cmdline. The cmdline carries
   `roothash=<dm-verity root hash>` and `dm-mod.create`, so the verified root is
   bound to the signed kernel, not to a mutable config file.
3. The initramfs mounts the squashfs with dm-verity. Hash mismatch aborts the
   boot rather than continuing with unverified content.
4. `overlayfs` gives `/etc` a tmpfs upper layer. Paths that must survive reboot
   (`/etc/machine-id`, hostname, network profiles, display config) are
   bind-mounted from `/var/etc` before the overlay is assembled.
5. State mounts, then OpenRC takes over.

`systemd-boot` is usable as the boot manager despite this being a systemd-free
system — it is a standalone EFI application with no runtime dependency on
systemd. GRUB is the fallback if its Secure Boot story proves simpler.

## Update flow

```
check  ->  download  ->  verify signature + hash  ->  write inactive slot
       ->  mark slot "trial"  ->  reboot  ->  health check
       ->  commit (clear trial)   or   auto-rollback
```

Details that matter:

- **Trial boots.** The boot counter lives in an EFI variable, not on disk, so it
  survives a broken state volume. After three boots that never reach a healthy
  session, the boot manager selects the previous slot.
- **Health check** means: display manager reached, `agentd` answered its socket,
  and no unit in a failed state for 60 seconds.
- **Deltas.** Full 6 GiB image downloads are unacceptable on metered links. Ship
  a content-defined chunk delta (zstd-framed) against the previous release, and
  fall back to the full image.
- **Signing.** Release artefacts are signed with an offline key; the public half
  ships in the image. A device that cannot verify a release does not install it,
  regardless of what the update server says.

## What counts as "the OS" vs. "the AI layer"

This boundary is easy to blur and expensive to get wrong.

| Changes with | Mechanism | Frequency |
|--------------|-----------|-----------|
| OS image | A/B update, reboot | monthly |
| AI runtime binaries | apk on the image, or Podman image | OS cadence |
| Models | content-addressed pull, no reboot | continuous |
| Container images | Podman pull, digest-pinned | weekly |
| Agent prompts / tools | signed data files in `/var/lib/aios` | continuous |

Models and container images must **never** require an OS update. The reverse is
also true: an OS update must never invalidate a pinned model by changing a
shared library underneath it. This is why model runners are versioned artefacts
with their own runtime, rather than Python packages installed into the system
interpreter.

## Secure Boot

Two supported configurations:

- **Secure Boot off.** Default for pre-1.0. Boots anything; dm-verity still
  detects tampering with the OS image but does not prove who built it.
- **Secure Boot on, our key enrolled.** Uses `sbctl`-style key management. The
  first-run flow must explain enrolment in one screen, not a wiki page.

Enrolling the NVIDIA module into our own key chain is a separate problem,
covered in [nvidia.md](nvidia.md#secure-boot).

## Installer

Open problem, and a larger one than it looks. Alpine has no graphical installer;
`setup-alpine` is a TUI. A desktop product cannot ship that.

Options under consideration:

1. **Custom graphical installer** modelled on postmarketOS's `pmbootstrap`-adjacent
   tooling. Full control, roughly a month of work.
2. **Image-based install**: ship a disk image and a tiny "write this to a USB"
   helper. Sidesteps partitioning UX entirely, but assumes whole-disk installs.
3. **Install from a running live session** using a small GTK/Qt frontend that
   drives `sfdisk` + `mkfs` + image write. Middle ground; still real work.

No decision recorded yet. This blocks every user-facing milestone.
