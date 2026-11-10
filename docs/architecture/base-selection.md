# Base platform selection

Evidence document supporting [ADR-0009](../adr/0009-reopen-base-selection.md).
Written because ADR-0001 accepted Alpine on a premise that has since changed.

## 1. The premise changed

ADR-0001 justified Alpine on smallness: small trusted base, fast boot, low idle
memory, declarative package set. That reasoning is valid — for a product whose
governing virtue is smallness.

Three answers have since changed the product definition:

| Stated | Consequence for the base |
|--------|--------------------------|
| Assistant-first shell | The shell is the product. The base is a host. |
| Local-first, cloud optional | A model runtime is mandatory on-device. |
| Public product, unknown hardware | Must install and work on machines we have never seen. |
| NVIDIA required | Vendor driver must be maintainable across kernels. |

Under those premises, the base is not judged on smallness. It is judged on
whether it can carry a public NVIDIA desktop product without consuming the
budget before the shell exists.

## 2. Derived requirements

### Must-haves — failing one is disqualifying

| ID | Requirement | Why it is disqualifying |
|----|-------------|-------------------------|
| M1 | Proprietary NVIDIA driver works on unknown hardware | The product requires NVIDIA and cannot ship FOSS-only to the public |
| M2 | Driver survives kernel updates **unattended** | Every kernel bump breaking the module is a support incident per user |
| M3 | Secure Boot with MOK enrolment | Public product, firmware default is Secure Boot on |
| M4 | Installer usable by a non-technical person | No TUI installer reaches a consumer |
| M5 | Atomic update with rollback | A bricked device is unrecoverable for a user who cannot debug it |
| M6 | Extensible Wayland compositor stack | The shell is the product; we must own the session |
| M7 | Reproducible custom image build | Otherwise every release is hand-assembled |
| M8 | A supportable update channel | We must ship fixes to strangers |

### Nice-to-haves — weighted

| Criterion | Weight | Rationale |
|-----------|--------|-----------|
| Ecosystem / package availability | 0.25 | Determines how much we build ourselves |
| Long-term maintenance burden | 0.25 | Determines whether we survive year two |
| Contributor familiarity | 0.20 | Determines how fast we move |
| Idle RAM | 0.10 | Directly competes with model memory |
| Security defaults / MAC | 0.10 | We execute model-generated commands |
| Boot time | 0.05 | Largely hidden by model load — see §4 |
| Disk footprint | 0.05 | Matters only on small disks |

The weights are a judgement call and should be argued with, not trusted.

## 3. Must-have matrix

`✓` passes · `◐` partial, needs work · `✗` fails

| Base | M1 | M2 | M3 | M4 | M5 | M6 | M7 | M8 | Passes |
|------|----|----|----|----|----|----|----|----|--------|
| Fedora atomic / bootc | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | **8** |
| NixOS | ✓ | ✓ | ◐ | ◐ | ✓ | ✓ | ✓ | ✓ | 6.5 |
| Debian | ✓ | ◐ | ✓ | ✓ | ◐ | ✓ | ◐ | ✓ | 5.5 |
| Arch | ✓ | ◐ | ◐ | ✗ | ◐ | ✓ | ◐ | ◐ | 3.5 |
| Alpine | ✗ | ✗ | ✗ | ✗ | ◐ | ◐ | ✓ | ◐ | **1.5** |
| Chimera | ✗ | ✗ | ✗ | ✗ | ✗ | ◐ | ◐ | ✗ | 0.5 |

Alpine fails four must-haves outright and needs work on two more. This is not a
matter of polish; there is no proprietary NVIDIA driver, no shim, no graphical
installer, and no automated answer to kernel/module drift.

### Weighted score (nice-to-haves only)

| Base | Score | Notes |
|------|-------|-------|
| Fedora atomic / bootc | **4.20** | Best ecosystem, best NVIDIA story |
| Debian | 4.05 | Close; needs a custom atomic layer |
| NixOS | 3.45 | Best reproducibility, worst familiarity |
| Arch | 3.40 | Best for one expert, worst for strangers |
| Alpine | 2.80 | Wins only the three lowest-weight criteria |
| Chimera | 2.00 | Interesting, not shippable |

Alpine ranks first on exactly the criteria that matter least here.

## 4. The numbers that actually decide it

All figures are **estimates to be replaced by measurement**; they are
order-of-magnitude, not benchmarks.

| Metric | Alpine | Fedora atomic | Delta | Who notices |
|--------|--------|---------------|-------|-------------|
| Installed base | 150–300 MB | 1.2–1.5 GB minimal, 4–6 GB workstation | 2–4 GB | only on ≤128 GB disks |
| Idle RAM, shell only | 250–400 MB | 500–700 MB | ~300 MB | ~2% of 16 GB |
| Boot to compositor | 2–3 s | 6–10 s | 4–7 s | nobody |
| 7B Q4 model load, NVMe mmap | 1–3 s | 1–3 s | 0 | everybody |
| Time to first token | model-load dominated | model-load dominated | ~0 | **this is the number** |

The argument collapses to one observation:

> **At the hardware tier this product requires — ≥12 GB VRAM, typically 32 GB
> RAM — Alpine's savings are 300–400 MB and five seconds of boot that the user
> never sees, because they are waiting for the model to load either way.**

We would trade CUDA, PyTorch, the desktop ecosystem, an installer, Secure Boot,
and automated driver maintenance for 1.2% of RAM and a boot stage hidden behind
model initialisation. That is not a close call.

Recompute this if the target tier changes. On a fanless 8 GB box, 300 MB matters
and the conclusion flips.

## 5. When Alpine is genuinely the right answer

Alpine is a defensible base for exactly one product shape:

**A fixed-hardware appliance.** If we sell the box, then:

- Unknown hardware disappears — one validated configuration.
- The NVIDIA driver is pinned to one kernel on one card; drift is our problem,
  scheduled deliberately.
- Instant-on becomes a real feature rather than an invisible one.
- Secure Boot keys are ours because the firmware is ours.
- Installer is unnecessary; the image is flashed at manufacture.
- No Calamares, no support matrix, no user-installable driver.

In that world Alpine's smallness is a *feature you can sell*: boots in three
seconds, runs on 8 GB, leaves everything for the model. That is a coherent
product.

It is not the product described here. "Public, unknown hardware" is the one
answer that removes every advantage Alpine has.

A second Alpine-compatible shape: a thin client where inference is entirely
remote. Fast, tiny, cheap. But local-first rules that out.

## 6. Recommendation

Three parts, in priority order.

### 6.1 Do not fork a distro yet

The shell is the product. Ship it as an installable session on an existing atomic
base before owning an OS.

Concretely: build the assistant shell as a Wayland session package, install it on
Fedora atomic (or a Bazzite/Bluefin derivative, which already solve NVIDIA plus
atomic plus desktop), and put it in front of people who did not build it.

This is the highest-value de-risking available, because it separates the two
risks that are currently entangled:

- **Does the shell actually work?** Answered in weeks, on real users.
- **Can we ship an OS?** Answered later, and only if the first answer was yes.

If the shell turns out not to be compelling, no OS work is wasted. If it is, the
base decision becomes an implementation detail with evidence behind it.

### 6.2 If a base must be chosen now: Fedora bootc

Passes every must-have without custom infrastructure:

- **`akmods`** rebuilds the NVIDIA module automatically per kernel. M2 is the
  single largest operational risk in this project and it is already solved here.
- **Shim + MOK** is a shipped, documented, deployed Secure Boot UX (M3).
- **bootc / ostree** is the immutable A/B model, already built (M5).
- **Anaconda / bootc install** plus Calamares availability (M4).
- Mesa, Wayland and kernel are current enough for NVK and compositor work (M6).
- **Bazzite exists.** Someone has already shipped NVIDIA + atomic + desktop to
  strangers. That is proof, not a projection.

### 6.3 Keep Alpine as the appliance SKU

Retain the Alpine work as a documented option for a known-hardware appliance
variant. Do not build it first.

## 7. What each recommendation costs

| Path | Cost | Risk |
|------|------|------|
| Shell on existing base | Weeks to first real feedback | Shell may not be compelling — cheap to learn |
| Fedora bootc fork | 2–4 months to installable image | Inherits Fedora's cadence and systemd; large base |
| NixOS fork | 3–5 months | Nix learning curve; smaller contributor pool |
| Alpine fork | 6–12 months | Four disqualifying gaps, each needing upstream-quality work |
| Appliance (Alpine, known HW) | 2–3 months | Must sell hardware; no public install path |

## 8. How to settle this with evidence

Timebox: two weeks. Do not start either fork before this completes.

1. Install the shell prototype on the current Fedora atomic or Bazzite image on
   the target GPU. Measure: time from power to first token, idle RAM, tokens/s.
2. Build the same prototype as a session on Alpine. Measure the same four
   numbers.
3. Compare against thresholds set in advance, not after seeing results:

   | Claim Alpine must justify | Threshold |
   |---------------------------|-----------|
   | Meaningfully faster to first token | ≥ 2 s faster |
   | Meaningfully less memory | ≥ 400 MB less at idle |
   | Meaningfully smaller installed | ≥ 2 GB less |

   Below all three, Alpine's must-have failures cannot be bought back.

4. Record the measurements in this document, replacing the estimates in §4.

If the numbers come out against Alpine — which §4 predicts — ADR-0009 resolves to
Fedora bootc, or to the shell-on-existing-base path if that is judged sufficient.
