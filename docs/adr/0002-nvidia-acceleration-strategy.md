# ADR-0002: NVIDIA acceleration strategy

- **Status:** Superseded by ADR-0014
- **Date:** 2026-11-10
- **Deciders:** project owner
- **Supersedes:** —
- **Superseded by:** ADR-0014

> **Superseded 2026-11-10.** This ADR's entire staging plan — FOSS-first, an
> opt-in acceleration pack, mandatory CUDA containers, a Turing hardware floor —
> was a consequence of musl, not of the product. With Fedora bootc the base is
> glibc and none of those constraints exist. See
> [ADR-0014](0014-nvidia-and-workloads-on-glibc.md). Retained as the record of the
> reasoning that drove the base change.

## Context

NVIDIA acceleration is required. The base is Alpine/musl (ADR-0001). These two
requirements are in direct tension.

As of 2026-11-10:

- Alpine's wiki states the proprietary NVIDIA driver is unavailable for musl;
  Nouveau is the supported path.
- Stock musl omits `R_X86_64_IRELATIVE` relocations and glibc's pthread mutex
  layout, both of which NVIDIA's userspace requires.
- On 2026-11-06, Chimera Linux published a working approach for driver branches
  580 and 620: GLVND, `gcompat`, `patchelf`, and a patched musl (`musl-nvidia`)
  adding ifunc support. Experimental, one maintainer, not shipped by any distro,
  not tested on Alpine.
- Nouveau + NVK is conformant Vulkan 1.4 and, since Mesa 25.1, the default
  OpenGL path for Turing and later. It delivers roughly 40–80% of proprietary
  performance, and no CUDA ever.
- Nouveau cannot reclock Pascal and Maxwell because the signing firmware was
  never released, making those generations unusable on the FOSS path regardless
  of driver conformance.

So the real choice is not "which driver" but "what does v1 promise".

## Decision

Adopt a **staged, FOSS-first strategy**:

1. **v1 ships path A.** Nouveau + NVK, no glibc shim, no vendor binaries.
   Accelerated inference through llama.cpp's Vulkan backend and equivalent Vulkan
   providers. Turing (RTX 2000 / GTX 1600) is the minimum supported generation.
2. **CUDA is explicitly out of scope for v1** and stated as such in the product,
   not buried in release notes.
3. **v1.5+ ships path B as an opt-in "acceleration pack"** — a separately
   installed apk that adopts Chimera's stack (patched musl, GLVND, gcompat,
   patchelf) and enables the proprietary driver.
4. **CUDA workloads run only in glibc containers**, never on the host, binding
   `/dev/nvidia*` and the host's `libcuda.so`. This is the standard NVIDIA
   container-toolkit model and avoids porting PyTorch.
5. **Path C (glibc VM with GPU passthrough) is not planned** but is the documented
   fallback if B proves unmaintainable.

The opt-in boundary is the important part of this decision. Users who want CUDA
self-select into an experimental component, breakage is contained to them, and
the default install remains a system we can reason about.

## Consequences

### Positive

- v1 ships in weeks rather than quarters, and it is a genuinely usable desktop.
- No vendor binary redistribution, licensing exposure, or Secure Boot key
  negotiation in v1.
- The default system keeps the security posture that motivated choosing musl.
- The AI layer is architected around containerised acceleration from day one, so
  path B is an additive change rather than a rewrite.

### Negative / costs

- **v1 cannot run Stable Diffusion, vLLM, TensorRT, LoRA training, or any CUDA
  workload.** This is a product limitation, not a technical detail, and it will
  lose users who expected "AI OS" to include image generation.
- v1 excludes all pre-Turing NVIDIA hardware. On Pascal and Maxwell, users get an
  unaccelerated desktop at boot clocks.
- Path B commits us to tracking every proprietary driver branch forever, plus
  owning a patched libc. That is the highest-maintenance commitment in the
  project.
- The ifunc support in `musl-nvidia` reintroduces exactly the relocation class
  musl excluded deliberately. It needs a security review we have not done.

### Neutral / follow-on

- Two supported hardware tiers appear: "works by default" and "works with the
  acceleration pack". Support burden doubles at v1.5.
- The VRAM warden in `agentd` must handle both a host driver and containerised
  drivers with the same lease semantics.

## Alternatives considered

**Proprietary driver from day one (path B only).** Rejected for v1 only. It puts
the highest-risk, least-proven component on the critical path of the first
release, and it is four days old.

**Abandon Alpine for a glibc base.** Rejected, but this is the honest fallback and
should not be treated as unthinkable. If two driver branches cannot be kept
working with reasonable effort, the base decision is the cheaper thing to change.

**AMD instead of NVIDIA.** Rejected — it changes the hardware requirement the
project owner stated. Worth noting that AMD is dramatically easier here, because
Mesa's RADV is fully open and musl-native; if the GPU requirement were negotiable,
this would be the recommendation.

**Software rendering / CPU only.** Rejected. It makes the product's central
feature unacceptably slow and does not meet the stated requirement.

**NVIDIA's open kernel modules with a glibc userspace in a container only.**
Rejected as the primary path because the host still needs a working driver for
the desktop session, which reintroduces the musl problem for display while adding
the container complexity for compute. It is a worse version of path B.

## Follow-ups

- **Determine the target GPU generation.** This is blocking. If it is Pascal or
  Maxwell, this ADR must be superseded before implementation.
- Security review of the `musl-nvidia` ifunc patch.
- Decide Secure Boot handling for out-of-tree modules (MOK enrolment vs. our own
  keys vs. requiring it off).
- Obtain legal review of NVIDIA redistribution terms before phase 4.
- Spike: Chimera's patch stack on Alpine 3.24 with driver 620, timeboxed to two
  weeks, to convert "experimental elsewhere" into "measured here".
- Instrument NVK performance on the target card with llama.cpp Vulkan, and publish
  tokens/second so expectations are set with numbers.
