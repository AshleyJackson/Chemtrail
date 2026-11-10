#!/usr/bin/env bash
# Wanted check: is the NVIDIA driver actually live?
#
# Wanted, not required. On a Secure Boot machine the module cannot load until the
# user enrols the MOK key, which happens on the first boot after install. A
# required check would fail that boot and greenboot would roll back a perfectly
# good deployment — a worse failure than a missing driver.
#
# Promote this to required once first-boot enrolment is automatic.
set -uo pipefail

if ! grep -qi '0x10de' /sys/bus/pci/devices/*/vendor 2>/dev/null; then
  echo "no NVIDIA GPU present; nothing to check"
  exit 0
fi

if [ -e /dev/nvidiactl ] && nvidia-smi >/dev/null 2>&1; then
  echo "NVIDIA driver loaded"
  exit 0
fi

echo "NVIDIA GPU present but the driver is not loaded (MOK enrolment may be pending)"
exit 1
