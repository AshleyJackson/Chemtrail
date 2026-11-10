# ADR-0014: NVIDIA, CUDA, and workload packaging on a glibc base

- **Status:** Accepted
- **Date:** 2026-11-10
- **Deciders:** project owner
- **Supersedes:** ADR-0002 (acceleration strategy), ADR-0003 (workload isolation)
- **Superseded by:** —

## Context

ADR-0002 planned a staged, FOSS-first strategy: ship Nouveau + NVK, defer CUDA to
an opt-in "acceleration pack" built on a patched musl, and run CUDA only in glibc
containers. ADR-0003 made those containers mandatory.

**Every one of those constraints was a consequence of musl, not of the product.**

With Fedora bootc (ADR-0013) the base is glibc. That single change removes:

- The need for a patched libc or `gcompat` shim.
- The prohibition on CUDA.
- The mandatory container indirection for PyTorch, vLLM, or anything from PyPI.
- The Turing hardware floor that Nouveau's reclocking limitations imposed.
- The FOSS-versus-proprietary driver trade-off as a product decision.

What remains is ordinary Linux NVIDIA integration, which is a solved problem with
well-known failure modes.

## Decision

### Driver

1. **Use the proprietary NVIDIA driver**, packaged through RPMFusion
   (`akmod-nvidia` / `kmod-nvidia`).
2. **Build the kernel module inside the image, at build time.** This is the key
   detail and it is *easier* on bootc than on mutable Fedora: the kernel and the
   module are shipped in the same artefact, so the classic akmods-versus-kernel
   race cannot occur. There is no runtime module compilation, no `kernel-devel`
   on the installed system, and no drift window.
3. **Never rebuild a module on the device.** If a kernel changes, it changes
   because a new image was deployed, and the module came with it.
4. **Pin the driver branch** in the image and treat a branch change as a release
   event with its own testing.

### CUDA

5. **CUDA is supported natively.** The toolkit comes from NVIDIA's Fedora
   repository where needed; the driver comes from RPMFusion. Do not mix the two
   for the driver.
6. **PyTorch CUDA wheels install normally** in a virtual environment. No
   container, no shim, no patched libc.

### Where AI workloads run

7. **Default: native, in a per-application virtual environment or a systemd
   service with its own `venv`.** This is now the simple path and it should be
   the default, because it is what users and tooling expect.
8. **Containers remain available and are used where pinning matters**: tooling
   that must not perturb the host, workloads with conflicting dependency trees,
   and anything a user wants reproducible by digest. They are a tool, not a
   requirement.
9. **`llama.cpp` stays a native binary.** It builds cleanly, has no dependency
   tree worth containerising, and benefits from direct GPU access.

This reverses the polarity of ADR-0003: containers move from mandatory to
optional.

### Hardware

10. **No Turing floor.** The proprietary driver supports Maxwell and later. The
    supported matrix is decided by test coverage, not by driver capability.
11. **VRAM is a quality target, not a capability gate**, following the
    availability of cloud routing (ADR-0011). State the recommended configuration
    and the minimum that still degrades gracefully.

### Secure Boot

12. **MOK enrolment is required and accepted.** Third-party kernel modules cannot
    be signed by the firmware trust store. One enrolment at first boot, with a
    clear explanation, is the cost of NVIDIA on any Linux distribution.

## Consequences

### Positive

- **The project's largest technical risk is gone.** Months of driver-porting,
  libc patching and container indirection are replaced by a package install.
- The accelerator ecosystem works: PyTorch, vLLM, TensorRT, diffusers, LoRA
  training, `bitsandbytes`, FlashAttention.
- A much wider hardware range is supported, which matters for a public product.
- Performance is the vendor's, not 40–80% of it.
- The "acceleration pack" concept — an experimental, opt-in, reversible component
  with legal exposure — is deleted entirely.
- Container images, if used, are ordinary and small, because they do not need to
  carry a duplicate CUDA stack.

### Negative / costs

- **Proprietary driver, permanent.** We adopt NVIDIA's licence terms, their
  release cadence, their suspend/resume bugs, and their Wayland history. This is
  the mainstream trade, but it is a real dependency.
- Secure Boot now requires MOK enrolment for every user, which is the least
  pleasant first-run step in the product.
- RPMFusion is a third-party repository; its availability and signing are part of
  our supply chain.
- We lose the "fully free software" position, which some users care about and
  some distributions make a selling point.
- Native Python environments reintroduce dependency conflicts on the host that
  containers had eliminated. The mitigation is discipline (per-app venvs), not
  architecture.

### Neutral / follow-on

- `nvidia-container-toolkit` becomes an optional convenience rather than a
  prerequisite.
- The GPU warden in [ai-runtime.md](../architecture/ai-runtime.md#gpu-arbitration)
  still matters, but for resource fairness, not for container plumbing.

## Alternatives considered

**Stay FOSS-only with Nouveau + NVK.** Retained as an explicit non-goal rather
than the default. It is now only relevant for users who refuse the proprietary
driver, and it costs 20–60% of performance with no CUDA. Offer it as a documented
alternative if at all, not as the shipping path.

**Keep the staged acceleration-pack model.** Rejected. It existed to contain the
risk of an experimental musl patch stack. With that stack gone, the staging has
no purpose and the opt-in boundary would only add friction.

**Containerise everything by default anyway.** Rejected. It was mandatory only
because of musl. Making it default on glibc would impose storage cost and cold
start for no benefit, and it fights how the Python ecosystem expects to work.

**Use NVIDIA's open kernel modules with the proprietary userspace.** Viable and
increasingly the vendor's preferred direction. Not chosen for v1 because RPMFusion's
packaging is the better-tested path; revisit when the open modules are the default
in the driver packages.

## Follow-ups

- Validate that a single image build produces a working driver on at least three
  GPU generations.
- Decide the MOK key strategy (ADR-0013 follow-up) and write the first-run flow
  copy. It must be one screen, not a wiki link.
- Test suspend/resume as a release gate; it is the historically worst area.
- Measure and publish time-to-first-token and tokens/second on the reference
  configuration, replacing the estimates in
  [nvidia.md](../architecture/nvidia.md).
- Write the "if the driver breaks" recovery path, including how a user boots the
  previous deployment.
- Reassess whether any workload still justifies a container now that the
  constraint is gone.
