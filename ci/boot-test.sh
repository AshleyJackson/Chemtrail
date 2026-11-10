#!/usr/bin/env bash
# Boot the image in QEMU and require a userspace that reaches multi-user.
#
# This is the first real gate: a build that compiles but cannot start is not a
# release. It needs a runner with /dev/kvm, which is why it is not on a hosted
# runner — see docs/architecture/release-engineering.md §11.
#
# UNVERIFIED: written against bootc-image-builder and qemu-kvm, but there is no
# KVM runner in the project yet, so this has not been executed end to end.
set -euo pipefail

image="${1:?usage: boot-test.sh <image@digest>}"
work="${WORKDIR:-build/boot-test}"
timeout_s="${BOOT_TIMEOUT:-180}"
mkdir -p "$work"

if [ ! -e /dev/kvm ]; then
  echo "no /dev/kvm: the boot gate needs a KVM runner" >&2
  exit 1
fi

# Build a disk image from the OCI image. The ISO is not needed for the gate and
# is slower; stable releases build it separately.
sudo podman run --rm --privileged --pull=newer \
  --volume "$work:/output" \
  --volume /var/lib/containers/storage:/var/lib/containers/storage \
  quay.io/centos-bootc/bootc-image-builder:latest \
  --type qcow2 --rootfs btrfs "$image"

serial="$work/serial.log"
qemu-system-x86_64 \
  -machine q35,accel=kvm -cpu host -m 4096 -smp 2 -nographic \
  -drive if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE.fd \
  -drive if=virtio,format=qcow2,file="$work/qcow2/disk.qcow2" \
  > "$serial" 2>&1 &
qemu=$!
trap 'kill "$qemu" 2>/dev/null || true' EXIT

deadline=$((SECONDS + timeout_s))
while (( SECONDS < deadline )); do
  if grep -qE 'Reached target .*Multi-User System' "$serial"; then
    echo "boot reached multi-user in $((SECONDS))s"
    exit 0
  fi
  if grep -q 'Kernel panic' "$serial"; then
    echo "kernel panic during boot" >&2
    tail -n 60 "$serial" >&2
    exit 1
  fi
  sleep 2
done

echo "timed out after ${timeout_s}s waiting for multi-user" >&2
tail -n 60 "$serial" >&2
exit 1
