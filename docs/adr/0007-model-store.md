# ADR-0007: Content-addressed model store

- **Status:** Proposed
- **Date:** 2026-11-10
- **Deciders:** project owner
- **Supersedes:** —
- **Superseded by:** —

## Context

Models are the largest and most valuable artefacts on the device. A single
quantised 70B model is 40 GB; a realistic library of a chat model, an embedding
model, a speech model, and a vision model is 60–120 GB. Users download them over
slow links, move them between machines, back them up, and delete them to reclaim
space.

The requirements that follow:

- **Integrity.** A model file is executable code, effectively. A tampered weight
  file can produce wrong or unsafe output and nothing will report it. It must be
  verifiable.
- **Deduplication.** Two manifests for the same base model with different chat
  templates share the same weights. Storing them twice wastes tens of gigabytes.
- **Resumability.** A 40 GB download over a domestic link will be interrupted.
- **Safe garbage collection.** Deleting a model must not delete a blob another
  model still references.
- **Portability.** The store must be a directory the user can `rsync`, not an
  opaque database.

`llama.cpp` uses GGUF files, which are already quantised and effectively
incompressible. Any design that assumes "archive and compress" is wrong for the
dominant format.

## Decision

Store models as **content-addressed blobs with separate JSON manifests**, on a
dedicated `/models` volume.

```
/models/
  blobs/sha256/ab/cd/<full digest>     # immutable bytes
  manifests/<name>.json                # metadata, references blobs
  refs/<name> -> manifest digest       # pinned human names
  tmp/                                 # resumable partial downloads
```

- Blobs are named by the SHA-256 of their contents and are never mutated.
- Manifests are small JSON documents describing format, quantisation, context
  length, capabilities, licence, provenance, and a list of blob references.
- A `refs/` entry maps a human name to a manifest digest, so pinning a name is
  atomic and obvious.
- Blobs are stored uncompressed. Manifests and tokeniser metadata are
  zstd-compressed; weights are not touched.
- A download lands in `tmp/`, is verified chunk by chunk, and only becomes visible
  when every blob in the manifest verifies. A partially downloaded model does not
  exist as far as the registry is concerned.
- Garbage collection is mark-and-sweep from `refs/` and live session references,
  never from "the last file that was used".
- Integrity is verified on load by default. Verification is skipped only behind an
  explicit per-model flag for development, because the cost on a 40 GB file is
  seconds and users will notice.

## Consequences

### Positive

- Deduplication is a consequence of the design rather than a feature: shared
  weights are physically shared.
- Integrity is checkable at any time with no sidecar checksum files to drift out of
  sync.
- Resumable downloads are natural: chunk verification does not depend on a partial
  file being at a particular length.
- The store is a plain directory tree. Backups, migration to a bigger disk, and
  moving models to a NAS are all `cp` or `rsync`.
- Provenance is recorded per manifest, which makes "where did this model come from"
  answerable — a prerequisite for any trust story.

### Negative / costs

- **Two-level indirection is more complex than a folder of files.** Users who
  expect `~/models/llama.gguf` will be confused, and tools that take a path to a
  GGUF need a resolve step.
- Deleting a "model" is not `rm`; it is unpinning a ref and waiting for GC. Users
  will delete a manifest and be surprised that space is not reclaimed until GC
  runs.
- Verifying a 40 GB blob on every load is measurable on slow disks.
- Blob-level deduplication does not work across *different quantisations* of the
  same model, which is the common case for a user trying a few quants. Only
  genuinely identical files dedupe.
- Hard links or reflinks are needed for the "export a model to an external path"
  flow, or that flow copies gigabytes.

### Neutral / follow-on

- The manifest schema becomes a public interface and needs versioning discipline.
- Import/export of a model between machines needs a manifest-plus-blobs bundle
  format (a tar with a fixed layout is sufficient).
- The registry is the natural place to record licence acceptance, which some model
  licences require.

## Alternatives considered

**Flat directory of GGUF files.** Rejected. Simplest possible thing and what most
users expect, but provides no integrity check, no deduplication, no provenance, and
no safe GC. It also makes resumable download the caller's problem.

**Follow Ollama's on-disk layout.** Rejected as a design, though it is close.
Ollama's blob store is content-addressed and works, but its manifests are internal
and it has no stable import/export or provenance story. Adopting it would mean
adopting its limitations. We should be able to *import* from it, which is a
migration feature, not a format decision.

**SQLite as the store.** Rejected. Tempting for querying, but it makes the models
opaque to the filesystem, breaks `rsync`-based backup, and puts tens of gigabytes of
binary into a database where a partial write is unrecoverable.

**OCI artefacts.** Rejected for v1. Genuinely elegant — models as OCI blobs with
manifests, reusing the container registry ecosystem and its tooling. Rejected
because it couples model distribution to registry infrastructure, makes local
management awkward, and adds a dependency that buys mostly what plain files already
provide. Worth revisiting if remote distribution becomes a first-class feature.

**Compressing everything with zstd.** Rejected. GGUF weights are quantised and do
not compress meaningfully; the CPU cost on every load is a direct tax on the
product's core function.

## Follow-ups

- Write the manifest schema with an explicit version field and a migration policy.
- Define the export bundle format and implement import from Ollama's layout.
- Decide GC trigger policy: on demand, on low disk, and on uninstall, with a grace
  period.
- Measure verification throughput on target hardware and set the default
  accordingly.
- Decide whether blobs may live on removable media, and how that interacts with
  verification and GC.
