# ADR-0003: Isolate AI workloads in Podman

- **Status:** Superseded by ADR-0014
- **Date:** 2026-11-10
- **Deciders:** project owner
- **Supersedes:** —
- **Superseded by:** ADR-0014

> **Superseded 2026-11-10.** Containerising AI workloads was mandatory because of
> musl. On Fedora's glibc base it is optional, and native virtual environments
> become the default. See
> [ADR-0014](0014-nvidia-and-workloads-on-glibc.md). The analysis below remains
> valid wherever a workload genuinely needs digest pinning or a foreign userland.

## Context

Most of the useful ML stack assumes glibc: PyTorch, vLLM, TensorRT, `bitsandbytes`,
FlashAttention, and the CUDA toolchain itself. The base system is musl
(ADR-0001). Even where a musl build exists, the version skew between what Alpine
packages and what a model requires is a recurring source of breakage — a model
that depends on `torch==2.x` cannot wait for the distribution to catch up.

There are three places this code could run:

1. **On the host**, installed into the system Python. Cheapest to start, and it
   silently makes the verified, read-only OS image mutable and unpinnable. It also
   means an ML dependency upgrade can break the desktop.
2. **In a chroot or `bwrap` jail.** Lighter than containers, but dependency
   management is manual and there is no image format, no digest pinning, and no
   reproducible acquisition story.
3. **In OCI containers.**

Separately, Rootless Podman is a native Alpine package, needs no daemon, and
composes well with a read-only root.

## Decision

All AI workloads that are not part of the OS image run in **rootless Podman
containers**, pinned by digest.

This includes, explicitly:

- Any CUDA workload, always (there is no other option on musl).
- Any Python workload requiring a version of PyTorch, vLLM, or Transformers that
  Alpine does not package at the required version.
- Anything requiring a glibc userland.

This excludes, explicitly:

- `llama.cpp` and `whisper.cpp`, which build natively against musl and are faster,
  smaller, and simpler as native binaries.
- `agentd`, which is native.
- Desktop components, which are OS image content.

Containers are not a universal hammer. Using one for a musl-native binary that
already works costs startup latency, storage, and an extra failure mode.

### Container rules

- Rootless. `podman` runs as the session user; there is no privileged mode and no
  `--cap-add` in the default policy.
- Digest-pinned. `image@sha256:…`, never a floating tag. Tags are chosen by
  whoever pushed them last.
- Device access only through the GPU warden's lease (see
  [ai-runtime.md](../architecture/ai-runtime.md#gpu-arbitration)), not by
  granting ambient `/dev/nvidia*`.
- Mounts are explicit and read-only by default. `/models` is mounted read-only;
  output paths are per-container scratch under `/var/lib/aios/scratch`.
- No network unless the workload's manifest declares it. A model runner that
  needs to download weights does so through `agentd`, not from inside the
  container.
- The image set is curated and signed. Users may add images, but doing so is a
  deliberate act with a warning, not a search-and-click flow in v1.

## Consequences

### Positive

- The host stays musl, verified, and immutable. An ML dependency crisis cannot
  break the desktop.
- Version skew disappears: a model pins its exact runtime, independent of Alpine's
  package cadence.
- Digest pinning gives reproducibility that `pip install` never will.
- Path B (ADR-0002) becomes additive: once the host driver works, the same
  containers simply gain device access.
- Rootless containers limit the blast radius of a hostile model or a compromised
  image.

### Negative / costs

- **Storage duplication.** Every container carries its own Python, CUDA libraries,
  and dependencies. A vLLM image is multiple gigabytes on top of the weights. This
  is the single biggest practical complaint this design will generate.
- Cold-start latency. Pulling and unpacking a large image on first use is slow, and
  it is a first-impression problem.
- Users cannot simply `pip install` what a tutorial told them to. That friction is
  real and needs a good answer in the UI, not a documentation link.
- Two runtimes to support (native `llama.cpp`, containerised everything else)
  doubles the matrix of "which path did this request take".
- Podman's rootless networking has edge cases with some inference servers binding
  to `0.0.0.0`; the port-forwarding model needs care.

### Neutral / follow-on

- We now own a curated image set and its signing. That is a real ongoing
  responsibility and an attack surface of its own.
- Container image updates follow a different cadence from OS updates, which is
  correct but needs a UI that can express it.

## Alternatives considered

**Install into the system Python on the host.** Rejected. It makes the immutable
root meaningless, creates unbounded dependency conflicts, and means an ML upgrade
can break the desktop session.

**Nix on top of Alpine.** Rejected as disproportionate. Nix would solve the
dependency problem elegantly, but it is a second package manager with its own
store, and it does not solve the CUDA/glibc problem — which is the actual blocker.

**`bwrap` only, no images.** Rejected for workloads, retained for tool execution
(ADR-0008). Without an image format there is no reproducible acquisition, no
digest pinning, and no way to ship a working CUDA userland.

**containerd + nerdctl / Docker.** Rejected. Both want a daemon, which is a root
service we would have to secure on a desktop. Podman is daemonless and native to
Alpine.

**A single fat "AI runtime" container for everything.** Rejected. One image
holding torch, vLLM, diffusers, and every CUDA library would be enormous, would
force version conflicts back into the image, and would be pinned to a single
driver branch.

## Follow-ups

- Define the curated image set and who signs it.
- Measure and publish cold-start times; if first-use latency exceeds a threshold,
  consider preloading the common image on install.
- Decide whether users may add arbitrary images in v1 or only in developer mode.
- Write the storage reclamation story: dangling images, unused layers, and the
  interaction with model GC.
