#!/usr/bin/env bash
# Turn the platform image into an installer ISO, for a VirtualBox smoke test.
#
# An OCI image is not bootable media, so something has to convert it.
# bootc-image-builder does that, but it pulls the image by reference: it cannot
# read another engine's local storage. The podman recipe shares
# /var/lib/containers/storage with the builder, which is podman-only. This uses
# the portable route instead: a throwaway registry on a private network, so the
# same script runs under podman or Docker, on Linux or under Docker Desktop.
#
# The ISO is interactive Anaconda on purpose. No kickstart, no answers baked in:
# the first question this image should answer is whether a human can install it,
# not whether a machine can.
#
# Output: build/iso/, holding the ISO and the builder's manifests.
set -euo pipefail
cd "$(dirname "$0")/.."

RUNTIME="${RUNTIME:-$(command -v podman >/dev/null 2>&1 && echo podman || echo docker)}"
BUILDER="${BUILDER:-quay.io/centos-bootc/bootc-image-builder:latest}"
BASE="${BASE:-quay.io/fedora/fedora-bootc:45}"
IMAGE="${IMAGE:-aios:dev}"
PORT="${PORT:-5000}"
ROOTFS="${ROOTFS:-btrfs}"
OUT="${OUT:-build/iso}"

network=aios-iso
registry=aios-iso-registry
volume=aios-iso-output
conf=aios-iso-conf
storage=aios-iso-storage
reference="$registry:$PORT/$IMAGE"

cleanup() {
  "$RUNTIME" rm -f "$registry" >/dev/null 2>&1 || true
  "$RUNTIME" network rm "$network" >/dev/null 2>&1 || true
  "$RUNTIME" volume rm -f "$conf" >/dev/null 2>&1 || true
  # $storage survives on purpose: it holds the copied image, and re-copying a
  # gigabyte on every attempt makes a failing build painful to iterate on.
  # Remove it with: podman volume rm $storage
}
trap cleanup EXIT

echo "--- runtime: $RUNTIME"

"$RUNTIME" network create "$network" >/dev/null

echo "--- building $IMAGE"
"$RUNTIME" build \
  --file Containerfile \
  --build-arg "BUILD_ID=${BUILD_ID:-dev}" \
  --build-arg "SOURCE_COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo unknown)" \
  --tag "localhost:$PORT/$IMAGE" \
  .

echo "--- starting a registry for the builder to pull from"
"$RUNTIME" run -d --name "$registry" --network "$network" \
  --publish "$PORT:5000" registry:2 >/dev/null

for _ in $(seq 1 30); do
  if "$RUNTIME" run --rm --network "$network" "$BASE" \
      curl -fsS "http://$registry:5000/v2/" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

"$RUNTIME" push "localhost:$PORT/$IMAGE"

echo "--- building the ISO from $reference"
"$RUNTIME" volume create "$volume" >/dev/null

# The builder pulls the image over the network, and this registry speaks plain
# HTTP, so it has to be declared insecure. Current builder releases have no
# --tls-verify flag. The config travels in a volume and is pointed at by
# environment variable: mounting it over /etc/containers would hide the image
# signature policy the builder also needs.
"$RUNTIME" volume create "$conf" >/dev/null
"$RUNTIME" run --rm --volume "$conf:/conf" "$BASE" \
  bash -c "printf '[[registry]]\nlocation = \"$registry:$PORT\"\ninsecure = true\n' > /conf/registries.conf"

# The builder also wants a containers/storage to work in, and says so plainly
# when it cannot find one. It is not the engine's storage: the image has to be
# present there under the same reference the builder is given, so it is copied in
# with skopeo rather than inherited from the engine.
"$RUNTIME" volume create "$storage" >/dev/null
"$RUNTIME" run --rm --privileged --network "$network" \
  --env CONTAINERS_REGISTRIES_CONF=/conf/registries.conf \
  --volume "$conf:/conf" \
  --volume "$storage:/var/lib/containers/storage" \
  quay.io/skopeo/stable copy \
  --src-tls-verify=false \
  "docker://$registry:$PORT/$IMAGE" \
  "containers-storage:$reference"

"$RUNTIME" run --rm --privileged --security-opt label=disable \
  --cgroupns=host \
  --network "$network" \
  --env CONTAINERS_REGISTRIES_CONF=/conf/registries.conf \
  --volume "$volume:/output" \
  --volume "$conf:/conf" \
  --volume "$storage:/var/lib/containers/storage" \
  "$BUILDER" build \
  --type anaconda-iso \
  --rootfs "$ROOTFS" \
  --output /output \
  "$reference"

echo "--- collecting the output"
mkdir -p "$OUT"
# Copy out through the engine API instead of piping a tar stream. A multi-gigabyte
# stream written from inside a container to a shared working tree stalls on hosts
# that mount that tree over a slow filesystem, which Docker Desktop does.
ctr="$("$RUNTIME" create --volume "$volume:/output" "$BASE")"
"$RUNTIME" cp "$ctr:/output/." "$OUT"
"$RUNTIME" rm -f "$ctr" >/dev/null
"$RUNTIME" volume rm "$volume" >/dev/null

iso="$(find "$OUT" -type f -name '*.iso' -print -quit)"
if [ -z "$iso" ]; then
  echo "no ISO under $OUT" >&2
  find "$OUT" -maxdepth 2 -type f >&2
  exit 1
fi

# An ISO is not an ISO because it ends in .iso: check the volume descriptor.
if [ "$(dd if="$iso" bs=1 skip=32769 count=5 2>/dev/null || true)" != "CD001" ]; then
  echo "$iso is not an ISO9660 image" >&2
  exit 1
fi

echo "iso:    $iso"
echo "size:   $(du -h "$iso" | cut -f1)"
echo "sha256: $(sha256sum "$iso" | cut -d' ' -f1)"
echo
echo "Next: docs/run/virtualbox.md creates the VM with EFI firmware and this ISO."
