# ADR-0021: The install is interactive and graphical

- **Status:** Accepted
- **Date:** 2026-11-11
- **Deciders:** owner
- **Supersedes:** —
- **Superseded by:** —

## Context

ADR-0020 makes the install medium thin: Fedora's netinstall image plus a kickstart
carrying one payload reference. The installs that proved it ran unattended — the
kickstart also supplied `clearpart`/`autopart`, `rootpw` and the locale, so
Anaconda never asked anything. That is right for a scratch VM and wrong for the
machine this is for. The product is a desktop OS: the person installing it has
their own name, their own password, and on a laptop often no wired network at all.
An install that supplies those answers itself leaves the machine with a root
password chosen by whoever wrote the kickstart and no account for its owner.

A kickstart cannot fix that by asking. Fedora 45's `pykickstart` offers `user`,
`rootpw`, `network` (with `--essid` and `--wpakey`) and `xconfig`, and no
`interactive` command: every answer is static or absent. The questions can only be
asked by the installer's own UI. And only its graphical UI can ask about wireless —
the text interface has no Wi-Fi configuration at all.

Two facts about Fedora 45's installer make this the right place to ask. Its
environment carries what a Wi-Fi install needs — `wpa_supplicant`, the
`fi.w1.wpa_supplicant1` D-Bus service, `libnm-device-plugin-wifi.so`, 199
`iwlwifi` firmware files and Anaconda's `pyanaconda.modules.network.device_configuration`
(measured from `images/install.img` on `Fedora-Server-netinst-x86_64-45-1.4.iso`) —
so a machine with no Ethernet can still install. And since Fedora 44 Anaconda
creates no default network profiles: only devices *configured during installation*
get a persistent profile, written to `/etc/NetworkManager/system-connections` on
the target. A Wi-Fi network joined in the installer therefore reconnects on first
boot, and skipping the step leaves the installed system with no network at all.

## Decision

The install is interactive and graphical. There is no unattended mode.

- `install/aios-netinst.ks` carries the payload reference, locale, keyboard,
  timezone, `graphical` and `xconfig --startxonboot`. It carries no `clearpart`,
  `autopart`, `rootpw` or `user`.
- `ci/build-netboot-iso.sh` adds `inst.graphical` to every boot entry and fails
  the build if the boot entries in the resulting image do not force it.
- Storage, the account and its password, and the network (Wi-Fi included) are
  answered by the person installing, in Anaconda's graphical UI, and written into
  the deployment.

## Consequences

### Positive
- The installed machine has its owner's account and password, and on a
  Wi-Fi-only machine it is on the network before anyone logs in.
- No credential is stored in the repository, embedded in a published medium, or
  known to anyone but the person installing.
- The one thing that has to be right on real hardware — wireless firmware and
  supplicant, then a saved profile — is exercised on every install, not only when
  someone remembers to test it.

### Negative / costs
- An install cannot be automated from this medium. Reinstall sweeps, CI installs
  and factory imaging need a different kickstart, which is a follow-up, not a
  configuration flag.
- Anaconda warns but does not block when no account is created, and this kickstart
  disables root, so skipping User Creation produces a system nobody can log into.
  A first-boot guard is a follow-up.
- The graphical installer needs a frame buffer that modesets; the media's "basic
  graphics mode" entry stays available for hardware where it does not.

### Neutral / follow-on
- Locale, keyboard and timezone remain pre-filled defaults. They are answers the
  person can change, not a mode.

## Alternatives considered

- **Keep the unattended kickstart and ask on first boot.** It installs the machine
  first and asks afterwards, through a component that does not exist yet, on a
  machine whose network may not work, with root's password already fixed by the
  kickstart. The questions are all ones the installer can already ask.
- **Ask in the text installer.** It cannot configure wireless, which is exactly the
  case that matters on a laptop.
- **Answer Wi-Fi in the kickstart with `network --essid --wpakey`.** It would work
  for one network, and it would publish that network's key in the repository and
  inside every medium built from it.

## Follow-ups

- A separate, deliberately unattended kickstart for reinstall and CI, kept out of
  the published medium.
- Catch the "install finished with no account" case at first boot, since the
  installer only warns.
