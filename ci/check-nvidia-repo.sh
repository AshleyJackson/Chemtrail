#!/usr/bin/env bash
# Preflight for the image build.
#
# Runs *inside* the pinned base image and answers one question: can this Fedora
# release and the RPMFusion NVIDIA packages be made to agree in a container
# build, with no mutable host and no runtime module build?
#
#   docker run --rm -v "$PWD/ci:/ci:ro" quay.io/fedora/fedora-bootc:45 \
#       bash /ci/check-nvidia-repo.sh
#
# Exits non-zero if the driver cannot be installed, because a release that
# builds without acceleration is worse than a release that does not build.
set -uo pipefail

fail=0
fedora="$(rpm -E %fedora)"
kernel="$(rpm -q kernel --qf '%{version}-%{release}.%{arch}')"
echo "fedora: ${fedora}"
echo "kernel: ${kernel}"

dnf install -y --setopt=install_weak_deps=False \
  "https://download1.rpmfusion.org/free/fedora/rpmfusion-free-release-${fedora}.noarch.rpm" \
  "https://download1.rpmfusion.org/nonfree/fedora/rpmfusion-nonfree-release-${fedora}.noarch.rpm" \
  || { echo "FAIL: RPMFusion release packages unavailable for Fedora ${fedora}"; exit 1; }

for pkg in akmods akmod-nvidia kernel-devel-matched; do
  if ! dnf repoquery --latest-limit 1 \
      --queryformat '%{name} %{version}-%{release}.%{arch}\n' "$pkg"; then
    echo "FAIL: ${pkg} not resolvable for Fedora ${fedora}"
    fail=1
  fi
done

if [ "$fail" -eq 0 ]; then
  dnf install -y --setopt=install_weak_deps=False \
    akmods akmod-nvidia kernel-devel-matched || fail=1
fi

if [ "$fail" -eq 0 ]; then
  akmods --force --kernels "$kernel" || fail=1
  echo "--- built kmod packages ---"
  ls -1 /var/cache/akmods/nvidia/ || fail=1
  echo "--- module on disk ---"
  find /usr/lib/modules -name 'nvidia.ko*' -print || true
fi

echo "--- build-only packages still installed (must be removed in the image) ---"
rpm -qa | grep -E '^(gcc|gcc-c\+\+|make|kernel-devel|akmods)' || true

exit "$fail"
