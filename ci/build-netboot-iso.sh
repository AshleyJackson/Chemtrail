#!/usr/bin/env bash
# Build the network-install medium: Fedora's netinst ISO with our kickstart
# embedded. Requires curl, sha256sum, xorriso and mkksiso (package lorax); runs no
# container runtime itself, so run it on a Fedora host or inside one with --privileged
# (mkefiboot needs losetup). Output: build/netboot/aios-netboot-x86_64.iso
set -euo pipefail
cd "$(dirname "$0")/.."

KICKSTART="${KICKSTART:-install/aios-netinst.ks}"
OUT="${OUT:-build/netboot}"
CACHE="${CACHE:-build}"
BASE_NAME="${BASE_NAME:-Fedora-Server-netinst-x86_64-45-1.4.iso}"
BASE_URL="${BASE_URL:-https://dl.fedoraproject.org/pub/fedora/linux/releases/45/Server/x86_64/iso}"
BASE_ISO="${BASE_ISO:-$CACHE/$BASE_NAME}"
RESULT_NAME="aios-netboot-x86_64.iso"
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

if [ "$(dd if="$iso" bs=1 skip=32769 count=5 2>/dev/null || true)" != "CD001" ]; then
  echo "$iso is not an ISO9660 image" >&2
  exit 1
fi

# mkksiso keeps the kickstart's basename.
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
