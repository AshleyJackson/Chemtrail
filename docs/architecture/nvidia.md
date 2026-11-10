# NVIDIA acceleration

> **Historical (2026-11-10).** This document analyses the musl constraint, which
> no longer applies: the base is now Fedora bootc (ADR-0013), where the
> proprietary driver and CUDA work natively. Retained because it is the record of
> *why* the base changed, and because the hardware matrix and failure modes remain
> accurate descriptions of NVIDIA on Linux.
>
> **Current strategy:** [ADR-0014](../adr/0014-nvidia-and-workloads-on-glibc.md).

This is the constraint that shapes the whole project. Every other architecture
document assumes the conclusions here.

> **Observation dates matter in this file.** The situation changed materially on
> 2026-11-06 and will change again. Re-verify before relying on any statement
> below.

## The base fact

Alpine's own wiki states that Nouveau is the supported NVIDIA driver and that
*the proprietary NVIDIA driver is not available for the musl C library.* Stock
musl lacks:

- `R_X86_64_IRELATIVE` relocations (ifunc), which NVIDIA's userspace uses. musl
  omits them deliberately — they are an arbitrary-code-execution primitive at
  load time.
- glibc's opaque pthread mutex layout and its static-initialiser behaviour, which
  NVIDIA's recursive mutex initialisation depends on.
- GLVND as the assumed dispatch layer.

None of these are packaging details. They are ABI and security-posture
divergences.

## What changed on 2026-11-06

Chimera Linux published *"Making musl and proprietary NVIDIA drivers work
together"*, with pull requests open for both the 580 (legacy) and 620 (current)
driver branches. The approach:

1. Switch the distribution to GLVND and rebuild Mesa against it.
2. Use a `gcompat` shim for vendor libraries that expect glibc symbols.
3. `patchelf` the vendor `.so` files to fix interpreter and RUNPATH assumptions.
4. Ship a patched musl (`musl-nvidia`, derived from Alpaquita's `musl-perf`)
   that adds ifunc relocation support.
5. Fix up mutex initialisation expectations.

Reported working on an RTX 3070 Ti with the 620 branch, partial on aarch64.
Described by its author as experimental with packaging still needing refinement.

This is real progress and it is four days old. It is one person's work, not
shipped by any distribution, and not validated on Alpine.

## The three paths

### A. FOSS only — Nouveau + NVK

Native musl, no glibc shim, no patch stack.

- Desktop: NVK is a conformant Vulkan 1.4 driver, and since Mesa 25.1 NVIDIA
  Turing and later get NVK+Zink as their OpenGL path by default.
- Compute: Vulkan only. `llama.cpp` and `whisper.cpp` have Vulkan backends.
  ONNX Runtime has a Vulkan execution provider.
- **No CUDA.** Therefore no PyTorch GPU, no vLLM, no TensorRT, no Stable
  Diffusion, no LoRA training, no `bitsandbytes`, no FlashAttention.
- Performance: roughly 40–80% of the proprietary driver, per the Chimera write-up
  and Collabora's own numbers.

This is what v1 ships.

### B. Patched musl + vendor driver

Adopt Chimera's stack: patched musl, GLVND, gcompat, patchelf.

- Desktop and CUDA get the real driver.
- CUDA workloads still need a glibc userland, so they run in Podman containers
  that bind in `/dev/nvidia*` and the host's `libcuda.so` — the same model the
  NVIDIA container toolkit uses everywhere.
- Cost: 2–4 person-months to reach stability, then permanent tracking of every
  driver branch, plus a security review of the ifunc patch (you are deliberately
  reintroducing a class of relocation musl rejected on purpose).

This is the opt-in acceleration pack, phase 4.

### C. Musl host + glibc AI guest

Keep the host pure and put a glibc distribution with full CUDA in a VM, using
VFIO passthrough or the newer `virtio-nvgpu` shared-device work.

- Clean isolation, no ABI hacking, host stays auditable.
- Costs: VM lifecycle UX, display integration, memory partitioning (a GPU that
  needs 12 GiB of host RAM reserved is a bad deal on a laptop), and the assistant
  can no longer see the GPU directly.
- Only worth it if the host must remain pristine for compliance reasons.

Not planned.

## Hardware matrix

The FOSS path's viability depends entirely on the card.

| Generation | Examples | NVK | Reclocking | Verdict |
|-----------|----------|-----|------------|---------|
| Blackwell | RTX 50xx | yes (Mesa 25.2+) | GSP | viable |
| Ada | RTX 40xx | yes, conformant | GSP | **best target** |
| Ampere | RTX 30xx | yes, conformant | GSP | **best target** |
| Turing | RTX 20xx, GTX 16xx | yes, conformant | GSP | viable, minimum |
| Volta | Titan V | yes | no signed FW | marginal |
| Pascal | GTX 10xx | yes | **no** — stuck at boot clocks | not viable |
| Maxwell | GTX 7xx/9xx | yes | **no** | not viable |
| Kepler and older | GTX 6xx/7xx | partial | no | unsupported |

Turing (RTX 2000 / GTX 1600) is the hard floor for v1. On Pascal or Maxwell the
card cannot leave its boot clock under Nouveau because NVIDIA never released the
signing firmware, so the desktop is unusable regardless of driver conformance.

**This is the most important unanswered question in the project.** If the target
hardware is Pascal, path A collapses and the choice is between path B and
abandoning the Alpine base.

## Secure Boot

An out-of-tree NVIDIA kernel module is not signed by the firmware trust store.
Three options, none free:

1. **MOK enrolment at first boot.** Works, but the flow is genuinely confusing
   for non-technical users and one mistimed keypress bricks the boot with an
   intimidating blue screen.
2. **Ship our own keys and enrol them.** Requires controlling the firmware's
   trust configuration; works on hardware we ship, not on hardware users already
   own.
3. **Require Secure Boot off for the acceleration pack.** Honest, simple, and
   reduces the security posture of exactly the users who opted into the risky
   component.

No decision. Tracked in [../README.md](../README.md#open-questions).

## Licensing and redistribution

NVIDIA's userspace libraries are proprietary. Shipping them in our image, or
downloading them on the user's behalf, has terms. The preview driver and the
datacenter driver have different redistribution rules. This needs a lawyer, not
an engineer, before phase 4 — it is the kind of thing that quietly kills a
product after launch.

The safe intermediate position: the acceleration pack is a script the user runs,
which downloads from NVIDIA directly and accepts NVIDIA's terms. Less polished,
legally simpler.

## Failure modes to expect

- **Driver/kernel ABI drift.** Every Alpine kernel bump can break the module.
  Pin the kernel for accelerator users, and do not auto-update them.
- **GLVND partial state.** A half-migrated GLVND setup produces `libGL` load
  failures that look like a broken desktop, not a driver problem.
- **GSP firmware mismatch.** Nouveau needs matching `linux-firmware-nvidia`
  content per chip; a missing `nvidia/<chip>/gsp/*.bin` presents as a hung
  session, not an error message.
- **VRAM accounting lies.** The proprietary driver reports free VRAM
  optimistically; the compositor then fails to allocate. Hence the warden's
  reserved headroom.
- **Suspend/resume.** Historically the worst area for both driver stacks. Test it
  as a release gate, not a bug report.

## Decision

Ship path A in v1 and be explicit in the product that CUDA is unavailable. Offer
path B as an opt-in pack once it can be maintained. Do not promise diffusion
models, fine-tuning, or vLLM in v1. Full reasoning in
[ADR-0002](../adr/0002-nvidia-acceleration-strategy.md).
