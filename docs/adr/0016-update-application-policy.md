# ADR-0016: Update application policy — two modes, no forced reboots

- **Status:** Accepted
- **Date:** 2026-11-10
- **Deciders:** project owner
- **Supersedes:** —
- **Superseded by:** —

## Context

The product owner's requirement: the user is offered two update behaviours,
**automatic** and **on restart**. The axis is right — it is the only update
decision a non-expert can reason about — but the wording carries an assumption
that has to be corrected before it reaches a screen.

> **An image-based OS cannot update without restarting.** The kernel, the NVIDIA
> module, and the compositor are one artefact and they are replaced together.
> There is no live-patch path for that, and we are not adopting one.

So neither mode can mean "no restart". What they can mean, and what this ADR
defines, is **who may initiate the restart**:

| Mode | The user's experience | Difference |
|------|----------------------|------------|
| **Automatic** | Never thinks about updates. The new version is simply there next time the machine starts. | The system may restart on its own, when idle and safe. |
| **On restart** | Is told an update is ready. Nothing changes until *they* restart. | The system never restarts itself. |

Both download in the background and stage before saying anything. The choice is
stored in `/var/lib/aios/update-policy`, which survives every deployment.
**Default: `auto`** — the product thesis is that the system acts unless told
otherwise, and the safety predicate in §3 is what makes that defensible.

### What bootc actually provides (observed 2026-11-10)

From `bootc-upgrades(7)` and `bootc-upgrade(8)`:

- `bootc upgrade` stages a deployment. By default it is applied **at shutdown**
  via `ostree-finalize-staged.service`. The running system is untouched.
- `--download-only` stages but keeps the deployment locked. A reboot *discards*
  it; the downloaded layers stay cached.
- `--from-downloaded` unlocks an already-staged deployment for application at the
  next shutdown or reboot, without re-fetching.
- `--apply` restarts immediately.
- `--soft-reboot=auto` restarts userspace only, with no kernel restart, when the
  target deployment supports it.
- `bootc-fetch-apply-updates.timer` ships enabled in Fedora bootc base images,
  runs daily, and reboots.

Two of those facts are load-bearing, and both push in the same direction: **the
default staging behaviour is already "applies on the next shutdown or reboot"**,
which is most of what "on restart" needs, and **the stock timer is unsafe for us.**

### Digest pinning removes the stock machinery

[ADR-0015](0015-release-channels-by-promotion.md) resolves a channel to a digest
and the device installs that digest.
bootc documents that with a digest image reference, `bootc upgrade` is always a
no-op and upgrades happen only through further `switch` operations.

That is the correct consequence of the manifest being the contract, but it means
we cannot use the stock update path at all: there is no tag to follow.

### The stock timer produces a rollback loop

`bootc-fetch-apply-updates.timer` checks, downloads, and reboots daily. Combined
with `greenboot` rollback:

```
bad digest promoted
  -> device applies it
  -> greenboot fails it and rolls back          correct
  -> timer fires 1-3 hours later                documented by Red Hat
  -> re-applies the same bad digest
  -> greenboot fails it and rolls back
  -> repeats until a human intervenes
```

The rollback works and is then undone. This is not hypothetical; Red Hat's own
documentation warns about it and tells operators to disable the timer. Shipping
it enabled would give us the worst possible failure: a machine that appears to
recover and then breaks itself again on a timer.

## Decision

### 1. Two modes, differing only in who may restart

**Automatic** (`auto`):
- Stage an unlocked deployment. It applies at the next shutdown or reboot.
- The system may additionally initiate that restart once the safety predicate in
  §3 holds continuously for five minutes.
- Never prompts. Never interrupts.

**On restart** (`on-restart`):
- Stage an unlocked deployment. It applies at the user's next shutdown or
  restart, whenever that is.
- Never restarts on its own.
- Shows a quiet, non-modal affordance: "Update ready — restart when convenient".

Both modes are the same `bootc switch` operation. The entire behavioural
difference is one policy bit. That is deliberate: two implementations of staging
would be two sources of bugs for no user benefit.

`--download-only` is **not** a mode. It is the hold used when a user says "not
now": the deployment stays locked for 24 hours, then unlocks. A shutdown during
the hold discards the staged deployment but keeps the cached layers.

### 2. Invariants that hold in both modes

1. **Never restart with an active, unlocked session.**
2. **Never restart while `agentd` reports an in-flight task that is not
   restart-tolerant.** This is the advantage an assistant-first OS has over a
   normal desktop: the system knows whether work is happening.
3. **Downloads need AC power or > 50 % battery.** Otherwise they pause and
   resume, and say so once.
4. **Deferral always works.** "Not now" is honoured for 24 hours and remembered.
5. **At most one notification per boot.** No modal dialogs about updates, ever.
6. **A discarded staged update is reported, never silently dropped.**
7. **All policy is local.** No telemetry, no account, no server-side device
   registry.

### 3. The safety predicate

`aios-updated` asks the system, not the clock:

```
safe_to_restart =
     no active unlocked user session
  && no in-flight agentd task marked restart-intolerant
  && (AC power or battery > 50%)
  && no download in progress
```

Automatic mode waits for this to be true continuously for five minutes, then
restarts. If it has not been true for seven days, the shell shows one line —
"Update ready — restart when convenient" — and stops waiting.

The seven-day fallback is what keeps `auto` from being useless on a machine that
is never idle. It degrades to `on-restart` behaviour rather than freezing.

### 4. Never retry a digest that rolled back

On rollback, append the digest to `/var/lib/aios/bad-digests` and never stage it
again on that device. The channel manifest's `supersedes` fixes the fleet; the
local blacklist protects the device in the window before the manifest is
corrected. Both are required — neither covers the other's latency.

### 5. Mask the stock timer

`systemctl mask bootc-fetch-apply-updates.timer` in the image. `aios-updated`
owns cadence, digest resolution, rollout eligibility, and the apply decision.

We are taking on the retry, backoff, and network-handling logic bootc would
otherwise have given us. That is the price of staged rollout and of not
boot-looping, and it is worth paying.

### 6. Soft reboot only where it is free

For deployments that do not change the kernel — shell-only or userspace-only
releases — use `--soft-reboot=auto` so the restart is a userspace restart rather
than a firmware cycle. It is an optimisation, never a promise, and it is never
offered for a driver or kernel change.

## Consequences

### Positive

- **The setting is three words a user can hold in their head**, and both options
  are truthful.
- **Neither mode can lose work**, because the restart is gated on the safety
  predicate rather than on a timer.
- The assistant-first design pays off: knowing whether a task is in flight makes
  automatic restarts genuinely safe, which a conventional desktop cannot claim.
- The rollback loop is designed out rather than discovered in production.
- Deferral, blacklisting, and withdrawal are one coherent story across device and
  fleet.

### Negative / costs

- **"Automatic" will disappoint someone who reads it as "no restart".** The UI
  copy carries real weight here and cannot be delegated to a tooltip.
- Two modes means two apply paths to test, and the safety predicate is the most
  likely place for a bug that loses a user's work.
- Masking the stock timer means owning scheduling, retries, and network failure
  handling that bootc ships for free.
- Digest pinning makes `bootc upgrade` a permanent no-op; any future bootc
  feature that assumes tag-following may not apply to us.
- **`on-restart` on an always-on desktop can mean never.** The escalation
  affordance helps; it does not solve it.
- Soft-reboot capability varies by backend (composefs differs from ostree), so
  this must be feature-detected, not assumed.

### Neutral / follow-on

- Adds a small always-running daemon and a shell affordance. Both are already in
  the component map.
- Establishes vocabulary: *staged*, *unlocked*, *held*, *blacklisted*. The shell
  must not use these words; the logs must.

## Alternatives considered

**A single automatic mode.** Rejected. Removing the user's control over restarts
on a machine they may be working on is the kind of thing that gets an OS
uninstalled. The two-mode choice costs almost nothing to implement.

**Follow mutable channel tags and keep the stock timer.** Rejected. It destroys
staged rollout and `supersedes` (both need a specific digest), makes tag mutation
unauditable, and reintroduces the rollback loop.

**Map "on restart" to `--download-only`.** Rejected as the primary mapping. A
shutdown discards a locked deployment, so a laptop user who only ever shuts down
would never update — the mode would silently do nothing for the people most
likely to choose it. Retained only as the 24-hour "not now" hold.

**Live kernel patching (kpatch/kGraft) to deliver a true no-reboot update.**
Rejected. It cannot cover a driver or compositor change, which is most of what we
ship, and supporting a live-patching stack is a commitment with no end.

**Always require an explicit user restart, in both modes.** Rejected. It
contradicts the stated requirement and makes the default path manual.

## Follow-ups

- Write the UI copy. Neither option may imply zero restarts.
- Confirm seven days as the idle fallback; make it a constant, not a policy file.
- Decide the deferral ceiling and escalation for security-relevant updates.
- Implement `aios-updated` and the safe-to-restart predicate; test lid-close,
  suspend/resume, and an always-on desktop.
- Feature-detect soft-reboot on the target backend rather than assuming it.
- Test the blacklist end to end with a deliberately bad digest.
- Add "restart blocked by: <reason>" to `aios update status`, so support can see
  which clause of the predicate is holding.
