#!/usr/bin/env bash
# Build the network-install medium: Fedora's netinst ISO with our kickstart
# inside it, so one file boots straight into an install of the published image.
#
# Why this and not bootc-image-builder: every format that builder offers embeds
# the container payload, and the smallest of them is 3.42 GB - past GitHub's
# 2 GiB per-asset limit before anyone argues about cost (ADR-0020). Fedora's
# netinstall media carry an Anaconda that understands the `bootc` kickstart
# command, so the payload can come from a registry at install time and this
# artefact stays close to the size of Fedora's own installer.
#
# The kickstart is pinned to a digest, not a tag, so this ISO installs exactly one
# image. Rebuilding it for a different image is a change to the pinned ref, which
# is the point: the medium is an artefact of a release, not a moving target.
#
# Requirements: curl, sha256sum, xorriso, and mkksiso (package `lorax`). This
# script deliberately does not call a container runtime - a nested "docker run"
# would hand the host daemon a container-local path and the bind mount would fail.
# Run it on a Fedora host, or inside one with the repository mounted:
#
#   docker run --rm -v "$PWD:/w" -w /w --entrypoint bash quay.io/fedora/fedora-bootc:45 \
#     -c 'dnf -y -q install lorax isomd5sum xorriso && bash ci/build-netboot-iso.sh'
#
# Output: build/netboot/aios-netboot-x86_64.iso
set -euo pipefail
cd "$(dirname "$0")/.."

KICKSTART="${KICKSTART:-install/aios-netinst.ks}"
OUT="${OUT:-build/netboot}"
CACHE="${CACHE:-build}"
BASE_NAME="${BASE_NAME:-Fedora-Server-netinst-x86_64-45-1.4.iso}"
BASE_URL="${BASE_URL:-https://dl.fedoraproject.org/pub/fedora/linux/releases/45/Server/x86_64/iso}"
BASE_ISO="${BASE_ISO:-$CACHE/$BASE_NAME}"
RESULT_NAME="aios-netboot-x86_64.iso"
# Fedora publishes checksums for the whole release directory under this name, not
# as a bare CHECKSUM. The tree has no CHECKSUM file, so guessing 404s.
CHECKSUM_NAME="${CHECKSUM_NAME:-Fedora-Server-45-1.4-x86_64-CHECKSUM}"
SUMS="$CACHE/$CHECKSUM_NAME"

for tool in curl sha256sum xorriso mkksiso; do
  command -v "$tool" >/dev/null 2>&1 || {
    echo "missing $tool; install lorax isomd5sum xorriso" >&2
    exit 1
  }
done

[ -f "$KICKSTART" ] || { echo "missing kickstart: $KICKSTART" >&2; exit 1; }

mkdir -p "$CACHE" "$OUT"

# The base installer is Fedora's, not ours: fetching it rather than rebuilding it
# is the whole reason this artefact is cheap. It is verified against the published
# CHECKSUM, because an installer that silently differs from the one Fedora tested
# is not worth shipping.
if [ ! -f "$BASE_ISO" ]; then
  echo "--- fetching $BASE_NAME"
  curl -fsSL -o "$BASE_ISO" "$BASE_URL/$BASE_NAME"
fi
if [ ! -f "$SUMS" ]; then
  curl -fsSL -o "$SUMS" "$BASE_URL/$CHECKSUM_NAME"
fi

echo "--- verifying the base installer"
expected="$(grep -F "($BASE_NAME)" "$SUMS" | awk '{print $4}')"
[ -n "$expected" ] || { echo "no checksum for $BASE_NAME in $SUMS" >&2; exit 1; }
actual="$(sha256sum "$BASE_ISO" | cut -d' ' -f1)"
if [ "$expected" != "$actual" ]; then
  echo "checksum mismatch for $BASE_ISO" >&2
  echo "  expected $expected" >&2
  echo "  actual   $actual" >&2
  exit 1
fi

echo "--- embedding $KICKSTART with mkksiso"
rm -f "$OUT/$RESULT_NAME"
mkksiso --ks "$KICKSTART" "$BASE_ISO" "$OUT/$RESULT_NAME"

iso="$OUT/$RESULT_NAME"
[ -f "$iso" ] || { echo "no ISO produced at $iso" >&2; exit 1; }

# An ISO is not an ISO because it ends in .iso: check the volume descriptor.
if [ "$(dd if="$iso" bs=1 skip=32769 count=5 2>/dev/null || true)" != "CD001" ]; then
  echo "$iso is not an ISO9660 image" >&2
  exit 1
fi

# The one thing that makes this medium ours is the kickstart, so prove it is in
# there rather than trusting the tool's exit status. mkksiso keeps the file's
# basename, so the path on the ISO is the basename of $KICKSTART.
ks_name="$(basename "$KICKSTART")"
if ! xorriso -indev "$iso" -find / -name "$ks_name" 2>/dev/null | grep -q "$ks_name"; then
  echo "the kickstart is not inside $iso" >&2
  exit 1
fi

base_size=$(wc -c < "$BASE_ISO")
iso_size=$(wc -c < "$iso")

echo "iso:    $iso"
echo "size:   $((iso_size / 1024 / 1024)) MiB (base installer $((base_size / 1024 / 1024)) MiB)"
echo "sha256: $(sha256sum "$iso" | cut -d' ' -f1)"
echo
echo "Boot it with the network attached: the installer pulls the image named in"
echo "$KICKSTART from its registry. Nothing installs without a route to it."
echo
echo "Note: that kickstart sets root's password to a known development value."
echo "This medium is for a lab VM; it is not a distribution image."
