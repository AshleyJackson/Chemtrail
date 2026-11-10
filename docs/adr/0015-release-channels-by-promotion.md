# ADR-0015: Release channels by promotion, not by branch merging

- **Status:** Accepted — revised 2026-11-10 (channel storage, single branch)
- **Date:** 2026-11-10
- **Deciders:** project owner
- **Supersedes:** —
- **Superseded by:** —

## Context

The product needs multiple release paths — nightly, weekly, stable — that a user
selects once and then follows automatically. Fully automated, built in GitHub
Actions.

The obvious design, imported from source-code release management, is branch
merging: work lands on `master`, and an automation merges `master` into `weekly`,
`weekly` into `stable` on a schedule.

That design has a fatal property for an operating system image:

> **Merging changes the tree, which changes the build, which changes the digest,
> which means you ship bytes that were never tested.**

The thing users receive must be bit-identical to the thing that passed the gates.
A merge-based pipeline guarantees it is not. Every merge is a new build with
slightly different inputs, so "stable" is never the artefact that soaked in
nightly.

There is a second problem. Image promotion is not a content operation. The
content is already correct; what changes is *how much confidence we have in it*.
Encoding confidence as divergent source branches means maintaining merge
conflict resolution on generated content — version pins, changelogs, lockfiles —
for no product benefit.

There is a third: the base is Fedora bootc (ADR-0013), where the OS *is* an OCI
image identified by digest. Registries already have a first-class mechanism for
"same artefact, different label". Using it costs nothing; fighting it costs
everything.

### Revision, 2026-11-10

Two things changed after review, both narrowing the original proposal:

1. **The channel pointer is a small signed JSON file committed to `channels/` on
   `master`**, not a hosted manifest service. Git history becomes the audit trail
   for free, and there is no new infrastructure to run.
2. **There is exactly one branch, `master`.** The long-support lineage
   (`extended`, formerly "LTS") is dropped from v1 — see
   [below](#why-extended-is-dropped).

GitHub Releases and tags are adopted for the **human-facing** record: each
promoted version becomes an immutable release, its tag locked to the build
commit, with artefacts and an attestation attached.

The distinction that makes this work:

| | GitHub Release | Channel file |
|---|---|---|
| Is | an **event** — "we shipped 1.4.0" | a **pointer** — "stable means this digest" |
| Changes | never | every promotion |
| Read by | humans, auditors, `gh` | the device, hourly |

A release cannot serve as a pointer, because "which release is stable?" has no
single answer across a list of releases. A file has exactly one answer.

## Decision

**One lineage, many pointers.**

1. **Exactly one build lineage consumes upstream change.** Every commit to
   `master` produces an image. Nothing else introduces new content into the
   channel chain.
2. **A release is a digest, not a build.** Promotion moves a pointer to an
   existing digest. It never rebuilds.
3. **Channels are signed JSON files, not mutable registry tags.**
   `channels/<name>.json` on `master`, written only by the promotion workflow,
   served over HTTPS from a stable URL. Each carries `{digest, version, rollout,
   supersedes}` plus a signature. Tags remain a convenience for humans and
   `podman`.
4. **No branch merging between channels.** `nightly`, `weekly` and `stable` are
   promotion stages over the same artefacts, not branches. All three are
   user-selectable settings.
5. **A shipped version is an immutable GitHub Release.** Tag `vMAJOR.MINOR.PATCH`
   points at the commit that built the image; the ISO, SBOM and signatures are
   attached before publication; GitHub's immutability locks the tag and assets
   and generates a release attestation. This is the provenance anchor and the
   human record. It is not the update pointer.
6. **Release versions are assigned at promotion, never baked at build.** The
   image records its *build* identity (date and commit). The user-facing version
   lives in the channel file and the release. Baking a version into the image
   would force a rebuild to promote it, which is the trap this ADR exists to
   avoid.
7. **Staged rollout is client-side and deterministic.** The channel file carries
   a percentage and a seed; each device buckets itself by hashing its machine ID.
   No telemetry, no accounts, no server-side device tracking.
8. **One branch.** No long-support lineage in v1.

Implementation detail in
[release-engineering.md](../architecture/release-engineering.md).

## Consequences

### Positive

- **The tested artefact is the shipped artefact.** This is the entire point. A
  digest that passed the hardware gates is the exact digest users receive.
- **Promotion is one commit.** Seconds, reversible with `git revert`, and
  auditable by anyone with the repository.
- **`git log channels/stable.json` is the promotion audit trail**, with no
  database to build or maintain.
- No merge conflicts on generated files, ever.
- Rollback is trivial at both ends: a device rolls back its deployment, and the
  channel can be rolled back to the previous digest.
- The pipeline is simple enough to reason about: one build, three pointers.
- Fully automatable end to end, which is the stated requirement.
- **Immutable releases give provenance, notes and downloadable artefacts for
  nothing** — and the attestation is real supply-chain evidence rather than a
  claim.

### Negative / costs

- **Promotion is not a rebuild, so a promotion never picks up newer upstream
  packages.** A fix that lands on Tuesday reaches stable via nightly soak, not by
  rebuilding stable on Friday. Correct, but it means stable lags by the soak
  period, and that latency must be a documented number, not a surprise.
- **Emergency security fixes need an explicit fast lane.** Without one, a critical
  CVE waits for soak. The lane exists in the design but it is a process, not a
  button, and it can be abused by habit.
- Users who think in "releases" will find "the same digest has three names"
  confusing until the versioning scheme is explained.
- Channel switching backwards (stable to nightly is forward; nightly to stable is
  a downgrade) needs a state-compatibility story that is not free.
- **Dropping `extended` removes the "nothing changes under me" option.** Users who
  need it have only `stable`, which still changes monthly. Honest for year one,
  and the first thing an enterprise will ask for.
- **Update resolution now depends on GitHub.** Devices keep working when it is
  down; they stop updating. `raw.githubusercontent.com` is also rate-limited per
  IP, which is fine for homes and risky behind large NATs.
- **`channels/**` is a high-value path.** Whoever can write it can redirect every
  device in the fleet. Branch protection and CODEOWNERS are mandatory, not advice.
- Git history interleaves promotions with code, which is occasionally annoying to
  read.

### Neutral / follow-on

- The channel URL is baked into the image, so changing it requires a release. Put
  a domain you control in front of it before that becomes expensive.
- Establishes a vocabulary: *build*, *digest*, *release*, *channel*, *promotion*.
  These must not be used loosely in the UI.

## Why `extended` is dropped

Fedora releases reach end of life in roughly thirteen months, and there is no
Fedora LTS. A channel promising "no feature changes for a year" must have
divergent content: a pinned older base plus backported security fixes. Divergent
content requires a branch and permanent cherry-pick work. There is no setting that
produces it.

The product owner elected a single branch for v1. That is coherent:

- Three channels are materially easier to explain than four.
- The promise was weak anyway — about thirteen months, not the years "LTS"
  implies.
- Maintaining a backport lineage is a permanent commitment that should be staffed
  before it is designed.

The cost is real and is recorded rather than hidden: there is no long-support
option. If it becomes a requirement, it needs a new ADR and a branch. It is not a
configuration change.

## Alternatives considered

**Automated branch merging (`master` → `weekly` → `stable`).** Rejected. It
rebuilds at every promotion, so the artefact that was tested is not the artefact
that ships; it creates permanent merge-conflict work on generated content; and it
conflates confidence with content. It is the correct model for a source-code
project with a stable ABI and the wrong model for an image-based OS.

**Rebuild per channel from the same commit.** Rejected. Reproducible builds would
make this nearly equivalent, but "nearly" is doing a lot of work, and bit-identical
rebuilds are a research problem for a C toolchain, a kernel, and a proprietary
driver. Promotion by digest avoids the question entirely.

**One channel only (rolling).** Rejected. A public product needs a slower path for
people who cannot debug their desktop.

**Mutable registry tags only, no channel file.** Rejected as the *contract*,
retained as a convenience. A tag cannot be signed independently, cannot carry a
rollout percentage, and cannot express "this tag now means a different digest" in
an auditable way. It also makes the client depend on the registry being reachable
for resolution rather than for bytes.

**Separate repositories per channel.** Rejected. Duplicates the Containerfile and
guarantees drift.

**GitHub Releases as the channel pointer.** Rejected. A release is immutable and
versioned; a pointer must move and must have exactly one current answer. "Which
release is stable?" is ambiguous across a release list, staged rollout cannot be
expressed, and `api.github.com` allows only 60 unauthenticated requests per hour,
which no fleet can poll. Retained for the human-facing record, where it is
excellent.

**A hosted manifest service (the original draft).** Superseded by files in the
repository. A git-committed file gets the audit trail, the access control, and
availability without running anything.

**A separate `channels` repository.** Considered. Cleaner permission separation,
but adds a repository and a cross-repository token for no benefit at this scale.
Revisit if `master` becomes crowded.

**A long-support branch.** Deferred, not rejected. See above.

## Follow-ups

- Protect `channels/**` with a ruleset and CODEOWNERS so only the promotion
  workflow can write it.
- Add `paths-ignore: ['channels/**']` to the build workflow, so promotions do not
  trigger builds.
- Choose the stable URL for channel files, and decide whether to front it with a
  domain now or later.
- Define the soak duration for each gate and publish it.
- Write the emergency security promotion process, including who may invoke it.
- Decide image and release-asset retention; both grow silently.
- Confirm a self-hosted GPU runner is available for the hardware gate.
- Revisit `extended` when there is a team to sustain it.
