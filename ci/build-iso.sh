#!/usr/bin/env bash
# Offline installer ISO from the image, for a VM smoke test.
#
# bootc-image-builder pulls by reference and cannot read another engine's storage,
# so the image goes through a throwaway registry on a private network.
# Output: build/iso/ (3.4 GB; see ci/build-netboot-iso.sh for the small medium).
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
  # $storage is kept: it holds the copied image, and recopying a gigabyte per
  # attempt makes iteration painful. Remove with: podman volume rm $storage
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

# The registry speaks plain HTTP and the builder has no --tls-verify flag, so it is
# declared insecure via CONTAINERS_REGISTRIES_CONF; mounting over /etc/containers
# would hide the image signature policy.
"$RUNTIME" volume create "$conf" >/dev/null
"$RUNTIME" run --rm --volume "$conf:/conf" "$BASE" \
  bash -c "printf '[[registry]]\nlocation = \"$registry:$PORT\"\ninsecure = true\n' > /conf/registries.conf"

# The builder needs the image in its own containers/storage, under the reference it
# is given.
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
# Copy out through the engine API: a multi-gigabyte tar stream into a bind mount
# stalls on Docker Desktop.
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

if [ "$(dd if="$iso" bs=1 skip=32769 count=5 2>/dev/null || true)" != "CD001" ]; then
  echo "$iso is not an ISO9660 image" >&2
  exit 1
fi

echo "iso:    $iso"
echo "size:   $(du -h "$iso" | cut -f1)"
echo "sha256: $(sha256sum "$iso" | cut -d' ' -f1)"
