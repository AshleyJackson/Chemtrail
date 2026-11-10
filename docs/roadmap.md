# Roadmap

Ordered by **risk retired per unit of effort**, not by component order. The
cheapest way to discover that the product does not work is to test the part that
might not work, first.

The previous version of this roadmap started with "build a bootable image". That
was wrong: it spent the budget on the solved part of the problem.

## Phase 0 — Settle the remaining unknowns (2 weeks)

**Goal:** remove the two assumptions that could still invalidate everything. The
base is decided (ADR-0013); what remains is the interface and the image.

- [ ] Compositor spike: `wlroots` versus `Smithay`, on summon latency, XWayland
      compatibility, fractional scaling, multi-monitor hotplug, input methods.
- [ ] Decide build-versus-fork for the compositor.
- [ ] Produce a minimal bootable Fedora bootc image: base, Mesa, NVIDIA module
      built at image time, no desktop environment.
- [ ] Prove the image boots, loads the driver, and updates via `bootc upgrade`
      with `greenboot` rolling back a deliberately broken deployment.
- [ ] Decide the minimum local model and recommended VRAM now that cloud routing
      makes the floor a quality target (ADR-0011, ADR-0014).

**Exit criteria:** a prototype that summons in under 50 ms; a bootc image that
boots, updates, and rolls back on reference hardware.

**Why first:** both cost months if wrong, and both are answerable with a fortnight
of work.

## Phase 1 — Interaction prototype on an existing desktop (4 weeks)

**Goal:** learn whether the interaction model is actually good, before building a
compositor to deliver it.

- Layer-shell assistant surface on an existing atomic base.
- Wired to a local `llama.cpp` CPU model and a cloud route behind the router.
- Window context from `wlr-foreign-toplevel-management` only.
- Tool execution through the sandbox, three-tier permissions.
- Put it in front of at least five people who did not build it.

**Exit criteria:**

- Users invoke it unprompted after the first day.
- The most common complaint is not "I don't know why I'd use this".
- A transcript of a real task completed end to end, without the developer
  intervening.

**Why here:** this is the cheapest possible test of the product's premise. If it
fails, the loss is four weeks rather than a year.

## Phase 2 — Shell v0 (3–4 months)

**Goal:** the assistant-first session, as its own compositor.

- Compositor per ADR-0010, assistant surface as the primary surface.
- Intent-driven window management.
- XWayland for legacy apps; documented list of what runs.
- Session lock, power management, notifications, portals.
- Accessibility baseline — decided in Phase 1, not deferred to 1.0.

**Exit criteria:**

- A full working day without falling back to a comparison session.
- Ordinary applications run and behave.
- Suspend/resume, multi-monitor, fractional scaling, and input methods work on
  the supported GPU.

## Phase 3 — Local inference at interactive speed

**Goal:** the loop feels like conversation.

- `llama.cpp` Vulkan on the target GPU.
- GPU warden: exclusive leases, VRAM headroom, graceful eviction.
- Model store with resumable download, verification, GC.
- Published time-to-first-token and tokens/second.

**Exit criteria:**

- ≥ 20 tok/s on the reference model, with the compositor never starved.
- Power-on to first token under 15 seconds.
- A model too large for free VRAM returns an explanation, not a crash.

## Phase 4 — Public beta as a session (2 months)

**Goal:** strangers can install the shell on their own machine.

- Session packaged for the chosen base, with an installer path that works without
  a wiki.
- Update channel for the session, independent of the OS.
- Recovery instructions tested by someone who has not read the design docs.
- Supported hardware matrix published.

**Exit criteria:**

- Ten people install it unaided.
- No install requires a terminal.

**Why before the OS:** this is the product, shippable without owning a
distribution. If it succeeds, Phase 5 is justified. If it does not, Phase 5 was
never worth starting.

## Phase 5 — Own the OS (4–6 months)

**Goal:** ship our own image, only after the shell has earned it.

- Production bootc image: pinned base, NVIDIA module built at image time, SELinux
  enforcing, no desktop environment.
- Installer ISO from `bootc-image-builder` with MOK enrolment in first-run.
- `greenboot` health checks for compositor, `agentd`, and GPU context creation.
- Signed images and signed release artefacts; device-side verification mandatory.
- Recovery: boot the previous deployment, and document it for a non-expert.
- Migration path for Phase 4 users.

**Exit criteria:**

- Clean install and in-place upgrade both tested on every supported configuration.
- A deliberately broken update rolls back unattended.
- Recovery accomplished by a non-expert with only the device.
- Image digest and driver version retrievable from the running system for support.

## Phase 6 — Acceleration pack (conditional)

Only if Phase 5 ships and CUDA demand justifies it. See
[nvidia.md](architecture/nvidia.md). Opt-in, reversible, clearly labelled.

## Explicitly out of scope, indefinitely

Multi-user or network-shared inference, on-device training, mobile convergence,
supporting arbitrary hardware configurations, and a vendor account for cloud
routing.

---

## Risk register

| Risk | Impact | Likelihood | Retired by | Trigger to act |
|------|--------|------------|------------|----------------|
| The interaction model is not compelling | Product has no reason to exist | Medium | Phase 1 | Users do not return on day two |
| Compositor takes far longer than modelled | 6–12 month slip | High | Phase 0 spike, Phase 2 | Phase 2 exceeds 4 months |
| Accessibility deferred forever | Excludes users; blocks a credible public release | High | Phase 1 decision | Any release without a plan |
| Base kernel and RPMFusion NVIDIA module diverge | Image builds without acceleration, or not at all | Medium | Phase 0 image, CI build | Any build where the module does not match the base kernel |
| Local latency below usable on target hardware | Assistant feels broken | Medium | Phase 3 | < 15 tok/s on reference model |
| Cloud routing leaks data by accident | Existential for trust | Medium | Phase 1 sandbox + audit | Any unauthorised egress |
| Tool sandbox bypassed by injection | Remote code execution | Medium | Continuous red-teaming | Any successful bypass |
| Installer underestimated | No public product | High | Phase 4 (session) and 5 | Any install needing a terminal |
| Support load exceeds capacity | Project stalls post-release | High | Phase 4 metrics | > 10 hours/week of support |
| Bus factor | Project dies with one person | High | Documentation, Phase 2 pairing | Any component with one author |

## Sequencing note

Phases 1 and 4 are deliberately shippable without owning an OS. That is the point:
the product's value is testable at every stage, and the expensive, undifferentiated
work is deferred until the differentiated work has proved itself.
