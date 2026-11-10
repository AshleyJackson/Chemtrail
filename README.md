# AI_OS

An assistant-first operating system: the user states intent, the system acts, and
applications are windows rather than the primary interface.

**Status:** pre-implementation, but no longer only prose. The base is settled as
Fedora bootc; the release pipeline exists as code and is exercised end to end
with dummy digests. There is no compositor and no shippable image yet.

Docs start at [docs/README.md](docs/README.md). The shortest path to the design is
[the Fedora bootc platform](docs/architecture/fedora-bootc.md) and
[release engineering](docs/architecture/release-engineering.md).

## What exists

```
Containerfile              platform image: base, NVIDIA kmod, session libraries, greenboot
ci/
  build-nvidia-kmod.sh     builds nvidia.ko against the image's own kernel, then strips the toolchain
  promote.sh               the only writer of channels/*.json
  boot-test.sh             QEMU boot gate (needs a KVM runner)
  hw-test.sh               GPU gate (needs a GPU runner)
.github/workflows/         build → check → boot-test → hw-test → promote
channels/                  the pointers; files appear on first promotion
tools/release/             promotion, gates, signing seam, device-side resolution
image/greenboot/           required and wanted health checks
docs/                      ADRs and architecture
```

## Try it

```bash
# Release logic, no image needed:
python -m unittest discover -s tools/release/tests -t tools/release
PYTHONPATH=tools/release python -m aios_release demo --out .demo

# Show what a device would decide:
PYTHONPATH=tools/release python -m aios_release resolve \
  --manifest .demo/channels/stable.json \
  --running-digest sha256:0000000000000000000000000000000000000000000000000000000000000000 \
  --machine-id "$(cat /etc/machine-id 2>/dev/null || echo demo-machine)"
```

Build the image (Linux, with a container runtime; the Docker Desktop engine on
Windows works):

```bash
docker build -t aios:local \
  --build-arg BUILD_ID="$(date -u +%Y.%m.%d)+glocal.r1" \
  --build-arg SOURCE_COMMIT="$(git rev-parse HEAD)" .
```

The first build is large: it upgrades the base, builds the NVIDIA module, and
removes the toolchain. Expect several minutes and several GB.

## What is not real yet

- **No compositor, no shell, no `agentd`.** The image is the platform only.
- **Boot and GPU gates have no runners.** `boot-test.yml` and `hw-test.yml` skip
  until `KVM_RUNNER` and `GPU_RUNNER` repository variables are set, because a
  green check that means nothing is worse than a visible gap.
- **Channel signing is a seam.** Local runs use an HMAC stub; CI expects
  `COSIGN_PRIVATE_KEY`. No channel has been published.
- **`channels/` is empty.** It gains files the first time a real promotion runs.
