# ADR-0005: KDE Plasma 6 as the desktop environment

- **Status:** Superseded by ADR-0010
- **Date:** 2026-11-10
- **Deciders:** project owner
- **Supersedes:** —
- **Superseded by:** ADR-0010

> **Superseded 2026-11-10.** This ADR made Plasma the desktop and the assistant a
> surface above it. The product decision is assistant-first shell, in which the
> compositor and shell are the product. See
> [ADR-0010](0010-assistant-first-shell.md). The comparison of desktop
> environments below remains useful for choosing a fallback comparison session.

## Context

Alpine packages several complete desktops on `edge`, including GNOME 51 and
Plasma 6.8 (Plasma 6.6.6 in the 3.24 stable branch). Both are actively maintained
by Alpine teams, and both run on musl.

The assistant surface is a separate concern and is decided in ADR-0006. This ADR
is about the desktop the user actually lives in.

What matters for this project specifically:

- **Wayland maturity with NVIDIA.** Historically the weakest combination. Both
  desktops are broadly fine on current drivers, but compositor-specific behaviour
  under load, on suspend/resume, and with fractional scaling still differs.
- **Window and workspace introspection.** An assistant that can reason about "what
  am I looking at" needs to know about the focused window, workspaces, and
  applications. This is compositor-specific and there is no standard protocol for
  it.
- **Resource footprint.** Whatever the desktop idles at is subtracted from the
  models.
- **Toolkit coherence.** The control panel and assistant should not be a second
  stack of dependencies bolted onto the first.
- **Packaging health on Alpine.** Community maintainers, not vendors, keep these
  alive.

## Decision

Ship **KDE Plasma 6 on Wayland** as the default and only supported desktop in v1.

Pin to the stable branch version (Plasma 6.6.x on Alpine 3.24) rather than tracking
`edge`, so desktop regressions are not introduced by unrelated package updates.

## Consequences

### Positive

- Qt 6 is the toolkit for the control plane UI as well, so there is one stack
  rather than two.
- Plasma's scripting surface (KWin scripts, Plasma extensions) is richer and
  better documented than GNOME Shell's for window-aware behaviour, which the
  assistant needs.
- Lower idle memory and CPU than GNOME in practice, which is directly convertible
  into model headroom.
- KWin's compositing and explicit-sync handling with NVIDIA has had more focused
  attention from KDE than Mutter has, and the KDE community is more responsive to
  NVIDIA-specific bug reports.
- Users can change almost everything, which matters on a small distribution where
  we cannot anticipate every workflow.

### Negative / costs

- Plasma is more configurable, which means more surface area for a user to reach a
  broken state we must support.
- KDE's release cadence is faster than Alpine stable's, so we sit on a version
  that is behind upstream and will receive fewer bug fixes during a release cycle.
- Qt 6 on musl has its own quirks (QProcess, locale-sensitive formatting) that we
  will hit and fix.
- Accessibility is weaker than GNOME's. This is a real trade-off, not a neutral
  one, and it should be revisited for a 1.0 release.

### Neutral / follow-on

- GNOME remains installable for testing, which gives us a way to distinguish
  compositor bugs from OS bugs.
- We inherit KDE's settings daemon architecture and its D-Bus surface.

## Alternatives considered

**GNOME 51.** The strongest alternative and genuinely close. Rejected on two
grounds: higher idle resource use, which is a direct cost to the product's core
feature, and a weaker introspection story for a compositor-aware assistant. Its
accessibility is better and that is a genuine loss.

**Sway / Hyprland.** Rejected. Lower footprint and excellent Wayland behaviour, but
they are not a desktop for non-technical users, and the target is a general-purpose
desktop. Attractive as an optional session for developers.

**Xfce.** Rejected. Lightweight, but its Wayland story is not ready and it would
cost us the modern compositor features the assistant integration depends on.

**COSMIC.** Rejected for v1. Promising and designed around this era of Wayland, but
too young to bet a release on, and its Alpine packaging is not mature.

**Our own shell.** Rejected. Building a compositor and shell is a multi-year
project that consumes the entire budget before any AI work happens.

## Follow-ups

- Prototype window-context introspection under KWin; establish what is actually
  reachable and what needs a KWin script or a portal extension.
- Test suspend/resume on NVIDIA under Plasma as a release gate, not a bug report.
- Decide the accessibility plan; do not ship 1.0 with GNOME-level accessibility
  unaddressed.
- Track Plasma versions in Alpine stable and define the policy for when a desktop
  security fix justifies an out-of-band image release.
