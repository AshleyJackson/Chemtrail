# ADR-0012: Public product scope

- **Status:** Accepted
- **Date:** 2026-11-10
- **Deciders:** project owner
- **Supersedes:** —
- **Superseded by:** —

## Context

The product owner has stated that this is a **public product**: unknown users, on
unknown hardware.

That is not a detail about distribution. It converts a set of deferred
conveniences into mandatory work, and it removes the two escape hatches that make
personal projects tractable: "it works on my machine" and "it's experimental".

The work this commits to, none of which a personal build needs:

- A graphical installer that a non-technical person can complete.
- Secure Boot that is on by default and does not require a wiki.
- Signed releases with a verifiable chain of trust.
- An update service that strangers can rely on, including rollback that works
  without a rescue USB.
- A documented hardware support matrix, and honest exclusions.
- A security disclosure policy and a response process for vulnerabilities in code
  we wrote and code we ship.
- Legal review of redistributing proprietary vendor binaries (ADR-0002).
- Documentation, onboarding, and a support channel.

## Decision

Build for public distribution, and let that constraint shape v1 rather than
retrofit it.

Specifically:

1. **Deliberately narrow v1.** Support `x86_64` with UEFI only. Support a
   published list of GPU generations, not "NVIDIA". Explicitly unsupported is a
   valid and documented answer.
2. **A device that cannot be installed is not supported.** Target hardware must
   have firmware whose Secure Boot story is known before it is listed.
3. **No experimental labelling as a shield.** Anything shipped to the public is
   either supported or not present. The acceleration pack (ADR-0002) is the one
   exception, and it must be opt-in, clearly marked, and reversible.
4. **Every release is installable from scratch and upgradable in place.** Both
   paths are tested, because a broken installer is invisible to existing users
   until it matters most.
5. **Support matrix is a document, not a promise in marketing.** It lists tested
   configurations and dates.
6. **Ship a recovery path before shipping the product.** A user must be able to
   restore a working system without our help and without a second computer.

## Consequences

### Positive

- Forces the genuinely hard problems — installer, signing, driver lifecycle,
  recovery — into the schedule instead of discovering them after launch.
- Prevents a v1 that only its authors can install, which is the most common
  failure mode for OS projects.
- A narrow, documented hardware matrix is easier to support than a broad, vague
  one, and is more honest to users.

### Negative / costs

- **Roughly an order of magnitude more work** than a personal daily driver.
- Cannot ship a shell without accessibility, because public means public.
- Legal costs and lead time, particularly around vendor binaries.
- Every additional hardware generation is a permanent testing obligation.
- Support load is unbounded in a way that engineering effort is not.
- A public product with a small team is a availability risk: a security
  vulnerability has to be fixed on someone's weekend.

### Neutral / follow-on

- Requires a release engineering function distinct from feature development.
- Requires a decision on funding, because a public product with a support
  obligation is not a hobby indefinitely.

## Alternatives considered

**Personal daily driver first, public later.** Rejected by the product decision,
but worth noting as the lower-risk path: it would let the shell be validated
before the support obligations exist. The shell-first delivery (ADR-0010 §5)
captures most of that benefit without delaying the product.

**Public but "beta" and unsupported.** Rejected. Users do not read the label, and
an unsupported public release still generates support load and reputational risk.

**Public on a single hardware SKU only.** Rejected for now, though it is the
cheapest route to a public release and would make an Alpine base viable
(base-selection.md §5). Reconsider if the support burden proves unsustainable.

## Follow-ups

- Write the supported hardware matrix, with tested dates.
- Define the release, signing and key-ceremony process.
- Write the security disclosure policy.
- Decide the funding and staffing model; a public product needs one.
- Write the recovery documentation and test it with someone who has not read the
  design documents.
