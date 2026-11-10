# ADR-0019: Do not ship XLibre, in any role

- **Status:** Rejected
- **Date:** 2026-11-10
- **Deciders:** project owner
- **Supersedes:** —
- **Superseded by:** —

## Context

The owner asked whether XLibre (<https://github.com/X11Libre/xserver>) could be
the display server *only*: present as the thing that draws, absent as a platform.
Two readings were possible, and both were tested against the pinned Fedora 45 base
on 2026-11-10 rather than argued from the fork's README.

### What was measured, 2026-11-10

- **XLibre cannot serve the Wayland session.** At tag `xlibre-xserver-25.1.11`
  (commit `ec1f2d37daa1450d8452abb547de4546321d7bb9`), `hw/` contains `kdrive`,
  `stubs`, `vfb`, `xfree86`, `xnest`, `xquartz` and `xwin`. There is no
  `hw/xwayland`, no file matching `*xwayland*`, and no Xwayland option in
  `meson_options.txt`. The fork does not carry a Wayland X server at all. COSMIC
  is a Wayland session, so an X11-only server cannot be behind it.
- **It does build.** `meson setup` and `ninja` complete on Fedora 45 (619 targets)
  with only the Xorg DDX enabled. "It will not compile" is not the objection, and
  it would have been the easiest one to answer.
- **Its driver ABI is incompatible with every driver we must run.** XLibre defines
  `ABI_VIDEODRV_VERSION` 28.1 and `ABI_XINPUT_VERSION` 26.0. Fedora 45's
  `xorg-x11-server-Xorg` 21.1.25 defines 25.2 and 24.4. The loader compares the
  major version, so a driver built against Fedora's headers is refused: the ABI
  tag also names its own module directory (`xlibre-25`), confirming the fork
  considers itself a separate ABI line. `xorg-x11-drv-nvidia`, the driver this OS
  exists to run ([ADR-0014](0014-nvidia-and-workloads-on-glibc.md)), is built
  against Fedora's headers and ships as a binary. It cannot load.
- **Upstream gives us nothing to lean on.** Releases are unsigned source tarballs,
  there is no Fedora package and no distribution CVE tracking, and the driver
  ecosystem around it is a set of separate forks. That is a weaker supply-chain
  position than Fedora's for a component that runs with elevated access to the
  display and input devices.

### The question underneath the question

The owner's real concern was scope: XLibre should be a display server and not a
platform, application framework, or desktop. That concern is answered by the
architecture, not by the choice of server — COSMIC owns the session, the assistant
owns one surface, and everything else is a package
([ADR-0018](0018-cosmic-desktop-for-v1.md)). Choosing XLibre would not have made
that boundary stronger, and it would have imported an unsupported ABI for the one
driver that must work.

## Decision

### 1. XLibre is not part of the image

No package, no build stage, no source tree, no vendored patch. The evaluated build
script was deleted rather than committed disabled, because a script that must not
run is a script someone will run.

### 2. Xwayland from Fedora is the only X server in the image

X11 applications are served by `xorg-x11-server-Xwayland`, started by `cosmic-comp`
as it starts today. It is updated by the same `dnf` transaction as the rest of the
image, tracked by Fedora's security process, and shares the ABI that third-party
drivers are built against.

### 3. There is no legacy X11 session in v1

No `/usr/share/xsessions` entry, no second server on `PATH`, no session picker
choice that starts X11. If that changes, the first candidate is Fedora's
`xorg-x11-server-Xorg`, which is ABI-compatible with the NVIDIA driver; adopting
it is its own ADR with its own test surface. XLibre is not the fallback.

### 4. The decision has a revisit condition, not a date

This ADR reopens if XLibre's driver ABI matches a driver we must run, which today
means the proprietary NVIDIA driver, or if Fedora stops shipping Xwayland. Absent
one of those, re-litigating it re-derives the same measurements.

## Consequences

### Positive

- **One driver ABI in the whole image.** The NVIDIA driver has exactly one
  consumer interface to satisfy, which is the interface Fedora builds against.
  Nothing in the release pipeline has to understand a second ABI line.
- **One X server, from one vendor.** Xwayland arrives as a package and leaves as a
  package. It appears in `dnf` history, in CVE feeds, and in the same rebuild that
  moves the kernel.
- **No toolchain stage for a privileged component.** Image composition stays a
  package install plus the NVIDIA module build. A second source build would add a
  pinned commit, a dependency set, a build cache and a failure mode to every
  release.
- **No unsigned privileged binary.** The image's display path is covered by
  Fedora's signing and provenance story.

### Negative / costs

- **There is no X11 session to fall back to.** Xwayland serves applications, not
  sessions. A user whose workflow needs a bare X11 session, a legacy WM, or
  X11-specific remote access has nothing here in v1.
- **The "X11 outlives Wayland" argument is left unanswered.** If Fedora drops
  Xwayland, this OS has no X11 path that does not involve adopting XLibre or
  maintaining a server. The risk is recorded in
  [fedora-bootc.md](../architecture/fedora-bootc.md) §11 rather than assumed away.
- **The rejection rests on numbers that upstream controls.** The ABI versions are
  a property of the fork at a point in time; the observation date is on the claim.

### Neutral / follow-on

- ADR-0013, ADR-0014 and ADR-0018 are unaffected. The X server was never part of
  the desktop decision; this ADR closes it separately.
- The X11 session that was considered and dropped was opt-in, so nothing in the
  shipped experience is removed by this ADR. What is removed is a second server,
  a build stage, and a test surface that would have existed in every release.

## Alternatives considered

**Make XLibre the display server, with COSMIC on top.** Impossible as stated.
XLibre has no Xwayland, and COSMIC requires a Wayland compositor; the only way to
run it underneath is to replace COSMIC with an X11 session, which reverses
ADR-0018.

**Add XLibre as an opt-in second X11 session.** This was the chosen direction
until the ABI measurement. It builds, and on a machine with Intel or AMD graphics
it would probably run. It cannot load the NVIDIA driver, so on the hardware this OS
targets it would fail at startup or fall back to a software path. A fallback that
does not accelerate the GPU is not a fallback; it is a bug report with a login
prompt.

**Patch XLibre's ABI numbers back to 25.2.** The numbers are 28 because the
internals diverged. Forcing the older number makes the loader accept binaries
compiled against a different struct layout, which turns a load failure into memory
corruption in a privileged process. Rejected.

**Build the NVIDIA X driver against XLibre's headers.** The kernel module builds
from source, but `nvidia_drv.so` does not; NVIDIA ships it as a binary. There is
nothing to rebuild, and no sign NVIDIA would support a fork's ABI.

**Ship Fedora's `xorg-x11-server-Xorg` as the legacy session.** Technically
viable: same ABI as the driver, same packaging, same security process. Not adopted
for v1 because no user has asked for a session rather than an application, and it
adds a second display stack to test in every release. This is the option that
comes back first if the requirement appears.

## Follow-ups

- When the desktop stage lands in the Containerfile, assert the decision instead
  of trusting it: no `Xorg` on `PATH`, no `/usr/share/xsessions` entry, and
  `xorg-x11-server-Xwayland` installed. A rejected alternative that can reappear
  silently is a decision without a test.
- If a legacy X11 session is requested, evaluate Fedora's Xorg first. XLibre is
  only reconsidered if its ABI matches a driver we must run.
- Track Fedora's Xwayland packaging every release. If it is dropped or
  unmaintained, reopen this ADR with the remaining options costed, including the
  cost of carrying a server ourselves.
- Any future claim about XLibre carries an observation date and the ABI numbers it
  was measured at. The fork moves.
