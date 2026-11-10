#!/usr/bin/env bash
# Promote exactly one channel. The only thing in the repository that writes
# channels/*.json.
#
# Inputs (environment):
#   CHANNEL          nightly | weekly | stable            (required)
#   CANDIDATE        override the digest selection        (optional)
#   NOW              ISO-8601 timestamp                   (default: now)
#   CHANNELS_DIR     default: channels
#   EVIDENCE_DIR     default: .evidence
#   EMERGENCY        1 to use the emergency lane          (default: 0)
#   APPROVERS        comma-separated names for emergency  (needed if EMERGENCY=1)
#   ALLOW_UNSIGNED   1 to skip signing (local only)       (default: 0)
#   DRY_RUN          1 to print the manifest and stop     (default: 0)
#   SIGN_COMMITS     1 to add -S to the commit            (default: 0)
#
# Exits 0 when there is nothing eligible. That is not a failure: a weekly run
# before anything has soaked should be quiet, not red.
set -euo pipefail

channel="${CHANNEL:?CHANNEL is required}"
channels_dir="${CHANNELS_DIR:-channels}"
evidence_dir="${EVIDENCE_DIR:-.evidence}"
now="${NOW:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"
candidate="${CANDIDATE:-}"
emergency="${EMERGENCY:-0}"
dry_run="${DRY_RUN:-0}"
allow_unsigned="${ALLOW_UNSIGNED:-0}"

export PYTHONPATH="${PYTHONPATH:-tools/release}"

mkdir -p "$channels_dir" "$evidence_dir"
work="$(mktemp -d)"
manifest="$work/$channel.json"
digest_short=""

if [ -z "$candidate" ]; then
  if ! candidate="$(python -m aios_release select \
      --channel "$channel" \
      --channels "$channels_dir" \
      --evidence-dir "$evidence_dir" \
      --now "$now")"; then
    echo "nothing eligible for ${channel} at ${now}; nothing to do"
    exit 0
  fi
fi
digest_short="${candidate#sha256:}"

args=(promote
  --channel "$channel"
  --candidate "$candidate"
  --channels "$channels_dir"
  --evidence-dir "$evidence_dir"
  --out "$manifest"
  --now "$now"
  --promotion-record-out "$evidence_dir/promotion-${channel}-${digest_short:0:12}.json")

if [ "$emergency" = "1" ]; then
  IFS=',' read -r -a approvals <<< "${APPROVERS:?APPROVERS is required for the emergency lane}"
  [ "${#approvals[@]}" -ge 2 ] || { echo "the emergency lane needs two approvers"; exit 1; }
  args+=(--emergency)
  for approver in "${approvals[@]}"; do
    [ -n "$approver" ] && args+=(--approved-by "$approver")
  done
fi

# Always promote unsigned first: the canonical payload is what gets signed, and
# signing it separately keeps any private key out of the Python process.
args+=(--unsigned)
python -m aios_release "${args[@]}"

if [ "$allow_unsigned" != "1" ]; then
  : "${COSIGN_PRIVATE_KEY:?COSIGN_PRIVATE_KEY is required unless ALLOW_UNSIGNED=1}"
  python -m aios_release payload --manifest "$manifest" --out "$work/payload.json"
  cosign sign-blob --yes --key env://COSIGN_PRIVATE_KEY --bundle "$work/payload.sig" \
    "$work/payload.json" >/dev/null
  python -m aios_release attach-signature --manifest "$manifest" \
    --signature-file "$work/payload.sig"
fi

python -m aios_release verify --manifest "$manifest"

if [ "$dry_run" = "1" ]; then
  echo "--- dry run: $manifest ---"
  cat "$manifest"
  exit 0
fi

install -m 0644 "$manifest" "$channels_dir/$channel.json"
git add "$channels_dir/$channel.json"
if git diff --cached --quiet; then
  echo "no change to $channel; nothing committed"
  exit 0
fi

version="$(python -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d.get("version") or "")' "$manifest")"
build_id="$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["build_id"])' "$manifest")"
source_commit="$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["source_commit"])' "$manifest")"

commit_args=(-m "release: promote ${channel} to ${candidate:0:19}")
message="build ${build_id}"$'\n'"digest ${candidate}"
if [ -n "$version" ]; then
  message+=$'\n'"version ${version}"
fi
commit_args+=(-m "$message")
if [ "${SIGN_COMMITS:-0}" = "1" ]; then
  commit_args+=(-S)
fi
git commit "${commit_args[@]}"
git push

if [ "$channel" = "stable" ]; then
  tag="v${version}"
  {
    echo "AI_OS ${version}"
    echo
    echo "- Build: \`${build_id}\`"
    echo "- Digest: \`${candidate}\`"
    echo "- Source: \`${source_commit}\`"
  } > "$work/notes.md"

  gh release create "$tag" \
    --draft \
    --target "$source_commit" \
    --title "AI_OS ${version}" \
    --notes-file "$work/notes.md"

  if compgen -G "dist/aios-*.iso" >/dev/null; then
    gh release upload "$tag" dist/aios-*.iso
  fi
  if [ -f dist/sbom.json ]; then
    gh release upload "$tag" dist/sbom.json
  fi

  gh release edit "$tag" --draft=false
  if gh release verify --help >/dev/null 2>&1; then
    gh release verify "$tag"
  else
    echo "::warning::gh release verify is unavailable; release was published unverified"
  fi
fi

echo "promoted ${channel} to ${candidate} (build ${build_id})"
