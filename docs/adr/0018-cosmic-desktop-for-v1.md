# ADR-0018: Ship COSMIC as the desktop environment for v1

- **Status:** Accepted
- **Date:** 2026-11-10
- **Deciders:** project owner
- **Supersedes:** ADR-0010
- **Superseded by:** —

## Context

The owner asked whether COSMIC, System76's desktop, could be the desktop
environment, and chose it for v1 on 2026-11-10. That answers a question ADR-0010
had answered the other way: that the session would be a shell we own, built on a
compositor we write.

The reversal is defensible on ADR-0010's own reasoning. Its consequences section
lists what stops being someone else's problem when we own the compositor — input
methods, accessibility, multi-monitor hotplug, fractional scaling, HDR, colour
management, screen sharing and portals, XWayland policy, clipboard, session
locking, power integration, notifications — and then calls the compositor "the
largest engineering commitment in the project", noting that "a mediocre one is
worse than Plasma". For a project of this size, that commitment is the most likely
reason the differentiated part, the assistant loop, never ships.

What this ADR reverses:

- **ADR-0010 §1**, that the session is a shell we own.
- **ADR-0010 §3**, that window management is the shell's job.
- **ADR-0010 §4**, that the implementation base is a `wlroots` compositor.

### What was verified, 2026-11-10

- Fedora 45 carries a `cosmic-desktop` group and the individual packages at
  **1.10.0**, including `cosmic-session`, `cosmic-comp`, `cosmic-greeter`,
  `cosmic-idle`, `cosmic-settings-daemon` and `xdg-desktop-portal-cosmic`. The
  base image can install the desktop without adding a third-party repository.
- `cosmic-greeter` requires `greetd` and `greetd-selinux`. Neither is in the base
  image, so the login path is ours to assemble.
- `cosmic-comp` is a Smithay-based compositor, and its binary contains the
  interface names `zwlr_layer_shell_v1`, `zwlr_foreign_toplevel_management_v1`,
  `toplevel_info` and `cosmic_toplevel`. Third-party layer surfaces and window
  enumeration are therefore implemented rather than absent. Interface names in a
  binary are strong evidence, not proof: Phase 0 confirms them at runtime.
- COSMIC Epoch 1 shipped 2025-12-11, with point releases roughly monthly since,
  and Epoch 2 and 3 already roadmaped. The stack moves quickly, which matters for
  how much of it we depend on.

### The part that is genuinely lost

The assistant is no longer the session. A user can ignore it and use COSMIC as an
ordinary desktop. ADR-0010 rejected exactly that outcome, and it was right to: the
difference between an AI-centric OS and an AI app is whether the assistant is the
interface or a window on it.

We accept that outcome knowingly, for three reasons. The overlay is still the
first thing the user reaches for at the moment of intent, because a global
shortcut summons it over anything. A product people can ignore is a better
failure than a compositor that arrives a year late. And the alternative does not
avoid the risk, it only delays discovering it.

## Decision

### 1. The desktop is COSMIC

COSMIC is installed from Fedora 45 packages in the image, pinned by digest like
everything else. No third-party COPR, no source build, no patches to COSMIC
components in v1. The desktop is part of the OS image, which means it is replaced
atomically with the rest of it.

### 2. The assistant is a layer-shell overlay, not an ordinary window

The assistant surface is a Wayland client on the `overlay` layer, which is what
`zwlr_layer_shell_v1` exists for. It is:

- summoned by a COSMIC custom shortcut (the product's primary gesture),
- given keyboard focus while visible, so typing reaches it without a click,
- dismissed to reveal applications unchanged.

An ordinary window would be the cheapest implementation and the wrong one. A
window can be buried, cannot be summoned over a fullscreen application without
cooperation, and reads as "an app" in the task switcher. The layer surface is the
only client-side mechanism that preserves "the assistant is what you address".

### 3. Window context comes from the protocols the compositor exposes

`wlr-foreign-toplevel-management` supplies the window list and basic actions.
COSMIC's own toplevel protocols supply whatever is richer. Intent-driven window
management is therefore bounded by upstream rather than by us.

When a required operation is missing, the order is: a patch upstream accepts, then
a protocol extension upstream accepts, then a fork. A fork is a separate ADR with
its own cost section, because it converts a packaged dependency into a
maintenance obligation.

### 4. Customisation is configuration, not patches

Shortcuts, theme, and applets we write ourselves. We do not patch `cosmic-panel`
or `cosmic-comp` for v1. The moment a local patch exists, the OS image can no
longer take an upstream update without conflict resolution, which is the same
failure mode the release design was built to avoid.

### 5. The app set is the desktop group, for now

`cosmic-files`, `cosmic-store`, `cosmic-term`, `cosmic-edit` and
`cosmic-player` ship because they are part of what makes a usable desktop, not
because they are the interface. Curating this list is a separate decision about
first-run experience, and it does not change the desktop decision.

### 6. Sequencing changes

The compositor spike in Phase 0 becomes a **COSMIC integration spike**, and the
compositor work leaves Phase 2 entirely. What Phase 2 gains instead is the
integration that makes the assistant better than a chat window: context from the
session, window actions, and the summon/dismiss semantics.

## Consequences

### Positive

- **Months leave the critical path.** The compositor, session management, greeter,
  portals, scaling, input methods, multi-monitor and XWayland are a package
  install rather than a multi-quarter project.
- **Accessibility stops being a from-scratch problem.** COSMIC's is younger than
  Plasma's and older than ours would have been on any realistic timeline.
- **The image gets simpler, not more complex.** No compositor source tree, no
  toolchain to build it, no protocol plumbing of our own. The same pinned-digest
  update model covers the desktop.
- **Upstream security and protocol work is inherited.** A compositor is a
  privileged attack surface, and one maintained by a desktop vendor is a better
  answer than one maintained by this project.
- **The assistant can be built against a real session immediately**, which is what
  ADR-0010 §5 wanted: ship the interface before shipping an OS.

### Negative / costs

- **The product's face is COSMIC's.** A reviewer may reasonably describe the
  result as "COSMIC with an assistant", and that perception is the thing ADR-0010
  was written to avoid. Differentiation now rests entirely on the overlay and the
  integration behind it.
- **The assistant is ignorable.** Users can use the desktop and never summon it,
  and the product's success metric becomes summon frequency rather than presence.
- **Intent-driven window management is bounded by upstream.** If COSMIC does not
  expose an operation, the assistant cannot do it.
- **Upstream velocity is a dependency risk.** Epoch 2 and 3 will change
  components we call into; the mitigation is that we pin a version and treat a
  desktop upgrade like a kernel upgrade, with the same gates.
- **Focus is the unproven assumption.** A layer surface that cannot reliably take
  keyboard focus, or cannot be summoned over a fullscreen game, degrades the
  product to a window. Phase 0 tests this first, before anything is built on it.
- **Accessibility is inherited, not solved.** COSMIC is not Plasma on assistive
  technology, and shipping COSMIC is not an accessibility plan.
- **Image size and update surface grow.** A desktop environment is now part of the
  OS: more packages to ship, more to boot, and a larger delta on every update. It
  also means a desktop regression can fail a boot, which is what the greenboot
  session check is for.

### Neutral / follow-on

- ADR-0006 (`layer-shell-assistant.md`) returns to relevance: the mechanism it
  proposed for a standalone assistant surface is now the mechanism this ADR
  depends on. Its status changes from "narrowed" to proposed again.
- ADR-0005 (Plasma) is not reinstated. It was superseded for treating a DE as the
  interface; this ADR accepts that premise but chooses COSMIC, and the comparison
  of desktops in 0005 remains superseded reasoning.
- The roadmap's Phase 2 shrinks and its Phase 4 packaging story changes: the
  session is no longer a separate artefact to package.

## Alternatives considered

**Build the compositor on wlroots as ADR-0010 decided.** Rejected by the owner,
and on merit: the cost of writing a compositor did not fall, while the cost of
shipping the assistant late did not change. Nothing in the last week made a
home-grown compositor cheaper.

**Install only `cosmic-comp` and write our own panel and launcher.** This is the
most interesting rejected option. COSMIC's shell surfaces are separate clients, so
this is technically available and would keep more of the interface ours. Rejected
for v1 as unnecessary scope: it re-opens the work the decision exists to avoid,
and it remains available later without changing the compositor.

**Plasma plus a layer-shell assistant.** Rejected again, for a new reason. KWin
would support the same overlay, but Plasma brings a heavier customisation surface,
a larger dependency tree, and a design language we would be fighting. COSMIC is
smaller, Rust, tiling-by-default, and already packaged in the release this project
pins.

**GNOME with a shell extension.** Rejected. The extension API is the lock-in
ADR-0010 named, and there is no supported path for a focus-holding overlay.

**Ship the desktop as a separate session artefact rather than in the image.**
Rejected for v1. It would decouple desktop updates from OS updates, but it splits
the atomic unit that makes rollback trustworthy, and the release design assumes one
image.

## Follow-ups

- **Phase 0 spike, before anything is built on it:** confirm at runtime that a
  layer-shell overlay can take keyboard focus, be summoned by a COSMIC shortcut
  over a fullscreen application, and receive the window list from
  `foreign-toplevel`. Measure summon latency against the 50 ms bar.
- Add `cosmic-session`, `cosmic-comp`, `cosmic-greeter` with `greetd`, and
  `xdg-desktop-portal-cosmic` to the Containerfile; decide whether the group or an
  explicit package list is the baseline.
- Verify COSMIC renders and scans out on the proprietary NVIDIA driver, and add a
  `greenboot` check for `cosmic-session` reaching its ready state.
- Resolve the shortcut conflict: COSMIC's launcher and the assistant both want a
  prominent key. Decide which yields, and make it visible.
- Write the interaction spec for summon, focus, dismiss, and what happens when an
  application holds a keyboard grab.
- Audit COSMIC's accessibility against the Phase 1 bar and record the gaps.
- Revisit the app set for first-run experience, separately from this decision.
