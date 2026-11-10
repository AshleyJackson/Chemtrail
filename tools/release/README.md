# Release tooling

The machinery behind [ADR-0015](../../docs/adr/0015-release-channels-by-promotion.md):
one build lineage, three moving pointers, no branch merging.

> A release is an immutable digest. Promotion moves a pointer. It never rebuilds.

Everything here is a pure function over plain data — no implicit clock, no
network, no subprocesses. CI supplies the clock, the evidence and the signature.
That is why the decisions are testable and reproducible.

## Commands

```bash
export PYTHONPATH=tools/release

# What is eligible right now?
python -m aios_release select --channel weekly --channels channels --evidence-dir .evidence

# Why is it eligible, or not? Prints every check.
python -m aios_release plan --channel weekly --candidate sha256:… --evidence-dir .evidence

# Write the next channel file.
python -m aios_release promote --channel weekly --candidate sha256:… \
  --channels channels --evidence-dir .evidence \
  --out channels/weekly.json --sign hmac:MY_KEY

# Stable only: take a 5% rollout to 100% after its soak.
python -m aios_release widen --channels channels --out channels/stable.json --sign hmac:MY_KEY

# Stable only: return to a known-good digest and record the bad one.
python -m aios_release withdraw --channels channels \
  --target-manifest previous-stable.json --out channels/stable.json --sign hmac:MY_KEY

# Device side: what should this machine do?
python -m aios_release resolve --manifest channels/stable.json \
  --running-digest sha256:… --machine-id "$(cat /etc/machine-id)"

# Exercise the whole pipeline with four dummy digests.
python -m aios_release demo --out .demo
```

`promote`, `widen` and `withdraw` refuse to run without an explicit signing
choice: `--sign hmac:<ENV_VAR>` for local use, or `--unsigned` when CI will attach
a signature (see `ci/promote.sh`).

## Evidence

Gates are facts about a digest, recorded by the workflow that observed them.
`.evidence/` is a CI artefact directory, not repository content.

| Kind | Written by | Means |
|------|------------|-------|
| `build` | `build.yml` | the image built, pushed, and here is its provenance |
| `image` | `check.yml` | `bootc container lint` passed |
| `boot` | `boot-test.yml` | the image booted to multi-user on a KVM runner |
| `hw` | `hw-test.yml` | the driver loaded and `cuInit` succeeded on a real GPU |
| `promotion` | `promote.yml` | a channel pointer moved to this digest |

**The promotion record is what a soak is measured from.** Not the channel
pointer: nightly moves on every commit, so "the digest nightly points at is seven
days old" is never true. An earlier draft of the gates made exactly that mistake,
and the test `test_weekly_uses_promotion_evidence_not_the_moved_pointer` exists
to keep it fixed.

Records are written with:

```bash
python -m aios_release record --kind image --digest sha256:… --commit "$SHA" \
  --check lint=pass --out .evidence/image.json
```

## Tests

```bash
python -m unittest discover -s tools/release/tests -t tools/release
```

The suite covers schema validation, canonical signing bytes, every gate,
candidate selection (including the pointer race above), version assignment,
widening, withdrawal, client-side resolution and the CLI end to end.

## Deliberately absent

- **A network client.** `resolve` is the decision, not the fetch. The device needs
  ~200 lines of HTTPS, ETag caching and `bootc switch`; none of that belongs in a
  pure function.
- **Real signing.** `DevHmacSigner` is symmetric and must never ship. CI uses
  `cosign sign-blob`; the public key ships in the image. The algorithm is chosen
  by the client's configuration, never by the file being verified.
- **Git operations.** `promote` writes a file. Committing, tagging and releasing
  live in `ci/promote.sh`, where they are visible.
