# ADR-0006: Assistant as a standalone layer-shell surface

- **Status:** Proposed — narrowed by ADR-0010
- **Date:** 2026-11-10
- **Deciders:** project owner
- **Supersedes:** —
- **Superseded by:** —

> **Narrowed.** ADR-0010 makes the compositor and shell our own, so this ADR's
> "capability provider" design is no longer the mechanism for window operations —
> the shell performs them directly. The parts that survive are the principles: the
> assistant is a client of the session, not a component of it, and no compositor
> internals leak into the assistant logic.

## Context

The assistant needs a persistent presence: summonable with a keybind, able to see
enough context to be useful, and able to act on the desktop. There are several ways
to attach it to the system, and the choice determines how much of our code is
disposable when the desktop changes.

Options span a spectrum:

- **Deep integration** — a GNOME Shell extension or a KWin script. Has access to
  everything the shell knows, and dies with the shell.
- **Surface-level integration** — a standalone application using
  `wlr-layer-shell` to draw a panel or overlay above normal windows. Portable
  across compositors, limited to what the protocol exposes.
- **A web application** in the browser. Maximally portable, minimally useful for
  desktop actions.
- **Replace the shell.** Total control, total cost.

The constraint that dominates: window and workspace *content* is not exposed by any
standard Wayland protocol. `wlr-foreign-toplevel-management` gives titles and
app IDs, not text. Reading what is on screen requires either a compositor
extension or screen capture plus OCR/VLM.

## Decision

Build the assistant as a **standalone application using `wlr-layer-shell`**, with
compositor-specific extensions added behind capability detection where the
standard protocol is insufficient.

Concretely:

- The assistant is a layer-shell client: a summonable overlay, plus an optional
  always-visible edge panel.
- It talks to `agentd` over the Unix socket. It holds no model or policy logic
  itself.
- Window context comes from `wlr-foreign-toplevel-management` where available:
  app ID, title, workspace.
- Anything beyond that (selected text, screen contents) is an explicit, per-use
  user action — a keybind that captures a region, or a clipboard read — never
  ambient.
- A thin KWin script is permitted as an **optional capability provider** for
  window actions (tile, move, focus). The assistant must remain functional with
  that provider absent.

The rule: the assistant is a client of the desktop, not a component of it. It must
survive a desktop swap with only the capability providers changing.

## Consequences

### Positive

- The bulk of the product's differentiating code is not tied to Plasma's internals
  or KDE release cadence.
- It works under Sway or Hyprland with no changes, which gives us a developer
  session and a fallback if Plasma proves untenable under NVIDIA.
- A crash in the assistant does not take the session with it, which matters when
  the assistant is executing commands.
- The layer-shell protocol is stable and well-supported by every compositor we care
  about.

### Negative / costs

- **Limited context.** Without deep integration the assistant cannot see text in
  other applications without an explicit capture step. This is a real product
  limitation and it will be the most common feature request.
- Screen capture plus a vision model is the workaround, and it costs GPU time and
  latency on exactly the hardware where GPU time is scarce.
- Some interactions that would be trivial in a shell extension (annotating windows,
  inline suggestions in a text field) are not possible.
- We maintain a capability-detection layer and at least one compositor-specific
  provider, so "portable" is not free.

### Neutral / follow-on

- Defines a small internal capability API (`window.list`, `window.activate`,
  `workspace.switch`) that providers implement. Third-party compositors could
  implement it later.
- The overlay's input handling needs care: a layer-shell surface that grabs focus
  can make the desktop feel broken.

## Alternatives considered

**GNOME Shell extension.** Rejected. Best possible context and the worst possible
lock-in; it also forces GNOME, which ADR-0005 declined. Not compatible with the
desktop decision.

**KWin script as the primary surface.** Rejected. It would give excellent context
and window control, but it ties the product to Plasma's internal API, which changes
between minor releases, and it cannot be tested outside a Plasma session. Retained
as an optional provider.

**Electron or Tauri web app in a normal window.** Rejected. A chat window that
cannot overlay, cannot be summoned globally, and cannot see the desktop is just a
chat app, which is the thing this project exists to be better than.

**Full shell replacement.** Rejected on scope. It is the honest end state for a
truly AI-native desktop and should be reconsidered for a 2.0, not attempted for v1.

**Wayland protocols only, no compositor-specific providers.** Rejected as too
limiting in practice; retaining providers keeps the option open while the core
stays portable.

## Follow-ups

- Prototype the layer-shell overlay on Plasma 6 and confirm focus and input
  behaviour do not degrade the session.
- Define the capability API and implement one provider.
- Measure the cost of screen-capture-plus-VLM as a context mechanism; if it is
  prohibitive on target hardware, the product story needs to change.
- Decide the keybind default and how it avoids colliding with common app shortcuts.
