#!/usr/bin/env bash
# Hardware gate: does this image's driver stack actually initialise on a GPU?
#
# The host's driver says nothing about the image's, so the check runs inside the
# image with the GPU mounted. Requires an NVIDIA GPU runner with the container
# toolkit and CDI generated.
#
# UNVERIFIED: written against nvidia-ctk CDI and podman, but there is no GPU
# runner in the project yet, so this has not been executed end to end.
set -euo pipefail

image="${1:?usage: hw-test.sh <image@digest>}"

if [ -z "$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null)" ]; then
  echo "no NVIDIA GPU on this runner" >&2
  exit 1
fi

sudo nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml >/dev/null

sudo podman run --rm --device nvidia.com/gpu=all --security-opt=label=disable \
  "$image" nvidia-smi --query-gpu=name,driver_version --format=csv,noheader

# cuInit is the smallest statement that the userspace driver can talk to a GPU.
# A module that loads but cannot initialise is exactly the failure this gate
# exists to catch.
sudo podman run --rm --device nvidia.com/gpu=all --security-opt=label=disable \
  "$image" python3 -c "
import ctypes
cuda = ctypes.CDLL('libcuda.so.1')
assert cuda.cuInit(0) == 0, 'cuInit failed'
print('gpu_context=pass')
"
