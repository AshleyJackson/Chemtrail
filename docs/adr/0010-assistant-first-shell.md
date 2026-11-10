# ADR-0010: The assistant-first shell is the product interface

- **Status:** Superseded by ADR-0018
- **Date:** 2026-11-10
- **Deciders:** project owner
- **Supersedes:** ADR-0005
- **Superseded by:** ADR-0018

## Context

The product owner chose **assistant-first shell**: the user states intent, the
system acts, and traditional applications are windows that are occasionally
opened. Not a normal desktop with an assistant bolted on.

This contradicts an assumption embedded in ADR-0005 and the architecture
overview, which treated "the desktop" as KDE Plasma and the assistant as a
surface floating above it. If the assistant is the interface, then whoever owns
the compositor owns the product experience — and if that is KDE, then KDE's
design decisions, release cadence and UX are the product.

It also changes what is on the critical path. Previously the OS came first and
the shell later. Now the shell *is* the differentiator and must come first.

## Decision

1. **The session is a shell we own.** It consists of a Wayland compositor, the
   assistant surface, and hosting for ordinary applications as Wayland and
   XWayland clients.
2. **The assistant surface is the primary surface**, not an overlay on a desktop.
   It is summoned by a global keybind, holds focus by default, and can be
   dismissed to reveal applications.
3. **Window management is the shell's job**, driven by intent as well as direct
   manipulation. Tiling, workspaces and window actions are compositor features,
   not plugins.
4. **Implementation base**: a `wlroots`-based compositor for v1, with `Smithay`
   (Rust) evaluated in parallel during the spike. `wlroots` is chosen for the
   maturity of its protocol coverage, XWayland handling and input stack;
   `Smithay` is the better long-term architecture if the team is willing to own
   more.
5. **Ship as a session before shipping as an OS.** The shell is delivered first
   as an installable session on an existing atomic base (ADR-0009), so that the
   interface can be evaluated without an OS project attached to it.
6. **Plasma and GNOME are retained only as comparison and debugging sessions.**
   They are not the product, and we do not customise them.

The compositor is the load-bearing choice in this ADR. Everything else follows.

## Consequences

### Positive

- The differentiation is where the user actually spends their time, which is the
  only way "AI-centric" means anything.
- We control focus, window policy, and context acquisition — the three things a
  standalone app cannot reach.
- Intent-driven window management becomes possible at all, rather than being
  approximated by a script against someone else's compositor.
- The product is separable from the distro, which is what makes the shell-first
  delivery path possible.

### Negative / costs

- **This is the largest engineering commitment in the project.** A usable
  compositor is months of work for a competent team, and a mediocre one is worse
  than Plasma.
- Everything the desktop environment provided is now ours: input methods,
  accessibility, multi-monitor and hotplug, fractional scaling, HDR, colour
  management, screen sharing and portals, XWayland policy, clipboard and primary
  selection, session locking, power management integration, notification
  protocol.
- Accessibility is the sharpest loss. Plasma and GNOME have years of investment;
  a new shell starts at zero, and retrofitting accessibility is expensive.
- Application compatibility becomes our problem. Bugs that users would attribute
  to "the app" will be attributed to us.
- The talent pool for compositor work is small, which concentrates risk in a few
  people.

### Neutral / follow-on

- Defines a shell-internal API for the assistant to request window operations,
  which replaces the capability-provider design in ADR-0006.
- Requires a decision on whether the shell is a fork of an existing compositor
  (Sway, niri, Hyprland) or built on the libraries directly. Forking buys a
  working product sooner and a harder upgrade path.

## Alternatives considered

**Plasma plus a full-screen layer-shell assistant.** Rejected as not
assistant-first. It is genuinely the fastest path to something usable and should
be built as a *prototype* to test the interaction model, but it cannot deliver
intent-driven window management, and it makes KDE's UX the product's face.

**GNOME Shell extension.** Rejected. Deepest context access, worst lock-in, and
GNOME's extension API breaks across releases. Also inherits GNOME's design
opinions, which are the opposite of a shell that gets out of the way.

**Fork Sway or niri rather than build on wlroots directly.** Attractive and not
excluded. It trades architectural control for a large head start. Decide during
the spike based on how much of the existing window logic survives the intent
model.

**Keep the OS-first sequencing.** Rejected. It spends the budget on packaging
before knowing whether the interface is worth packaging.

## Follow-ups

- **Two-week compositor spike**, evaluated against: global summon latency under
  50 ms, XWayland app compatibility, fractional scaling, multi-monitor hotplug,
  and input method support. Compare `wlroots` and `Smithay` on the same criteria.
- Decide fork-versus-build after the spike.
- Write the accessibility plan before any public release. Shipping a shell without
  one excludes users and is not a deferrable detail.
- Define the assistant-to-compositor API for window operations.
- Decide the XWayland default and the fallback story for apps that will not run.
- Prototype the interaction model on Plasma first, where it is cheap, to learn
  what users actually want before building the compositor.
