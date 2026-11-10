#!/usr/bin/env bash
# Build the NVIDIA kernel module inside the pinned base image.
#
# Two facts discovered by running this against fedora-bootc:45 (2026-11-10):
#
#   1. The base image's kernel lags Fedora updates (7.2.15 in the image, 7.3.3
#      in updates). Installing kernel-devel-matched therefore upgrades the
#      kernel. Read the kernel version *after* installing, never before, or the
#      build fails with "Could not find files needed to compile modules".
#   2. akmod-nvidia pulls the userspace driver, which the image wants anyway.
#
# STRIP=1 removes the build toolchain afterwards and reports whether the module
# survives. That is the question that decides single-stage versus builder-stage.
set -euo pipefail

fedora="$(rpm -E %fedora)"

echo "--- upgrading the base to the kernel that will ship ---"
dnf -y upgrade --setopt=install_weak_deps=False

dnf install -y --setopt=install_weak_deps=False \
  "https://download1.rpmfusion.org/free/fedora/rpmfusion-free-release-${fedora}.noarch.rpm" \
  "https://download1.rpmfusion.org/nonfree/fedora/rpmfusion-nonfree-release-${fedora}.noarch.rpm"

dnf install -y --setopt=install_weak_deps=False \
  akmods akmod-nvidia kernel-devel-matched

kernel="$(rpm -q kernel --qf '%{version}-%{release}.%{arch}')"
echo "--- building nvidia.ko for ${kernel} ---"
akmods --force --kernels "$kernel"

mkdir -p /rpms
cp -v /var/cache/akmods/nvidia/*.rpm /rpms/
echo "--- module on disk ---"
find /usr/lib/modules -name 'nvidia.ko*' -print

if [ "${STRIP:-0}" = "1" ]; then
  echo "--- removing build-only packages ---"
  dnf remove -y akmods akmod-nvidia kernel-devel kernel-devel-matched gcc make || true
  echo "--- module after removal ---"
  find /usr/lib/modules -name 'nvidia.ko*' -print
  echo "--- leftovers ---"
  rpm -qa | grep -E '^(gcc|make|kernel-devel|akmods|akmod-nvidia)' || echo "none"
  echo "--- installed nvidia packages ---"
  rpm -qa | grep -i nvidia || true
fi
