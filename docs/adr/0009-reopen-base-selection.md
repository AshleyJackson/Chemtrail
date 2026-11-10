# ADR-0009: Reopen the base platform decision

- **Status:** Accepted — base resolved by ADR-0013
- **Date:** 2026-11-10
- **Deciders:** project owner
- **Supersedes:** ADR-0001
- **Superseded by:** —

## Context

ADR-0001 accepted Alpine Linux with musl as the base. Its justification was
smallness: small trusted base, fast boot, low idle memory, declarative package
set.

Three product answers have invalidated that premise:

1. **Assistant-first shell.** The shell is the product's face. The base is a host
   for it, not the thing users interact with.
2. **Local-first inference, cloud optional.** A full model runtime is mandatory
   on-device.
3. **Public product on unknown hardware.** It must install and work on machines
   we have never seen, including firmware with Secure Boot enabled.

Under those premises the base must satisfy: proprietary NVIDIA on unknown
hardware, unattended driver survival across kernel updates, Secure Boot with MOK
enrolment, a consumer-grade installer, atomic updates with rollback, an
extensible Wayland compositor stack, reproducible image builds, and a supportable
update channel.

Alpine fails four of these outright and needs substantial work for two more. It
scores first on exactly the criteria with the lowest weight — boot time, idle RAM,
disk footprint — and those savings are invisible at the hardware tier the product
requires. Full analysis in
[base-selection.md](../architecture/base-selection.md).

## Decision

1. **Reopen the base decision.** ADR-0001 is superseded and no longer binding.
2. **Do not fork any distribution yet.** Build the assistant shell as an
   installable session on an existing atomic base and validate it with real users
   first.
3. **If a base must be selected now, it is Fedora bootc** — the only candidate
   passing every must-have without custom infrastructure.
4. **Retain Alpine as a documented option for a known-hardware appliance SKU**,
   where unknown hardware, installer, Secure Boot and driver drift all disappear.
5. Set the validation thresholds in
   [base-selection.md §8](../architecture/base-selection.md#8-how-to-settle-this-with-evidence)
   before running the comparison, and record the measurements publicly.

The decision to reopen is final. The replacement decision is deferred to
evidence, not to preference.

## Consequences

### Positive

- The project stops spending its budget on undifferentiated packaging before the
  differentiated component exists.
- The largest operational risk (NVIDIA module versus kernel ABI) is inherited
  solved rather than invented.
- The shell can be in front of users in weeks, which is the only way to learn
  whether the product's premise holds.
- If a fork happens later, it happens on a measured foundation.

### Negative / costs

- **Discards the Alpine architecture work as the primary path.** The documents
  remain valid for the appliance variant and for their reasoning, but the
  implementation plan built on them is void.
- Commits to systemd if the Fedora path is taken, which has its own complexity and
  a larger base image.
- Accepts a 1.2–1.5 GB base and 300–400 MB of extra idle RAM, permanently.
- Means the product is, for now, a session on someone else's OS. That is a
  positioning problem as much as a technical one.
- Adds a validation phase before implementation, which will feel like delay.

### Neutral / follow-on

- ADR-0003 (Podman isolation) and ADR-0004 (immutable A/B) were derived from the
  Alpine constraint. Their reasoning survives; their specific mechanisms may be
  replaced by ostree/bootc semantics.
- If the appliance SKU proceeds, Alpine returns — with a completely different
  justification (known hardware, instant-on) rather than a generic one.

## Alternatives considered

**Keep Alpine and push through.** Rejected. It requires building an installer,
solving Secure Boot without a shim, maintaining a proprietary driver on musl, and
carrying a driver/kernel drift burden — four upstream-quality projects before the
product's actual differentiator exists. The measured benefit is 300–400 MB and a
boot stage the user never sees.

**Choose Fedora immediately without validation.** Rejected as premature. The
shell-first path may make the question moot, and a two-week measurement is cheap
compared with a fork.

**Purchase a glibc distribution and strip it.** Rejected. Stripping is how you
obtain a large base with the support properties of neither the original nor a
purpose-built one.

**NixOS.** Retained as the strong second. It wins on reproducibility and rollback
and loses on contributor familiarity. If the team is small and highly technical,
revisit before committing to Fedora.

**Abandon the OS ambition and ship an application.** Not rejected on technical
grounds. It is the honest comparison point for §6.1, and if the shell cannot
justify system-level integration, this is the correct outcome.

## Follow-ups

- Run the two-week validation and replace the estimates in
  [base-selection.md §4](../architecture/base-selection.md#4-the-numbers-that-actually-decide-it).
- Write the shell-first delivery plan and rewrite the roadmap around it.
- Revisit ADR-0003 and ADR-0004 once the base is settled; their mechanisms depend
  on it.
- Decide explicitly whether the appliance SKU is in scope for year one.
- If Fedora is chosen, document the derivative policy: which Fedora components we
  pin, and how we handle an upstream regression.
