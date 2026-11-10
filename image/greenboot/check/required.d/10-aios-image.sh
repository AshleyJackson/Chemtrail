#!/usr/bin/env bash
# Required check: a deployment that cannot identify itself, or that has lost its
# kernel module, is broken and should be rolled back.
#
# Deliberately hardware-independent. This must pass on a machine with no NVIDIA
# GPU, because failing here rolls the deployment back.
set -euo pipefail

if [ ! -s /usr/lib/aios/build-id ]; then
  echo "missing /usr/lib/aios/build-id"
  exit 1
fi

if ! ls /usr/lib/modules/*/extra/nvidia/nvidia.ko* >/dev/null 2>&1; then
  echo "nvidia.ko is missing from this deployment"
  exit 1
fi

echo "image $(cat /usr/lib/aios/build-id) intact"
