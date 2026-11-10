# Release engineering

Implementation reference for
[ADR-0015](../adr/0015-release-channels-by-promotion.md): how nightly, weekly and
stable are produced, promoted, signed, and consumed.

## 1. The invariant

> A release is an immutable digest. Promotion moves a pointer. It never rebuilds.

Everything below follows from that one sentence.

## 2. Why branch merging breaks it

```
merge-based (rejected)                    promotion-based (chosen)

master ─merge─> weekly ─merge─> stable    master ─build─> digest A
        |          |          |                            │
      rebuild    rebuild    rebuild                      promote
        |          |          |                            ▼
     digest B   digest C   digest D                   weekly = A
                                                         │
                                                      promote
                                                         ▼
                                                    stable = A

  three builds, three digests,              one build, one digest,
  tested B, shipped D                       tested A, shipped A
```

The left side loses the property the whole pipeline exists to provide. It also
produces merge conflicts on generated files (pins, changelogs, lockfiles) that
somebody has to resolve, forever, for no benefit.

## 3. Artefact identity

Each build records:

| Field | Where | Example |
|-------|-------|---------|
| `build_id` | image label, immutable | `2026.11.10+g1a2b3c4d.r42` |
| `source_commit` | image label | `1a2b3c4d…` |
| `base_digest` | image label | `sha256:…` |
| `nvidia_branch` | image label | `620` |
| `digest` | registry | `sha256:…` |
| `version` | channel file, assigned at promotion | `1.4.0` |
| `release_tag` | GitHub Release, assigned at promotion | `v1.4.0` |
| `channel` | device state, `/var/lib/aios/channel` | `stable` |

**Do not bake the release version into the image.** If `version` were an image
label, promoting would require a rebuild, which is the exact failure this design
avoids. The running system reports `build_id` (from the image) and `version` (from
the channel file it was installed under). Bug reports should include both plus the
digest.

Versioning:

- Nightly `build_id`: `YYYY.MM.DD+g<sha7>.r<run>`. The run number is what keeps a
  cron rebuild of an unchanged commit distinguishable from the push build. Every
  build identity therefore maps to exactly one digest.
- Stable `version`: `MAJOR.MINOR.PATCH`, assigned when the digest is promoted.
- Release tag: `v` + that version, pinned to the **build** commit, not to a merge
  commit. `git checkout v1.4.0` therefore lands on the exact source that produced
  the shipped image.

## 4. Channels and gates

| Channel | Source | Promotion gate | Cadence | Support |
|---------|--------|----------------|---------|---------|
| `nightly` | every `master` build | image builds, `bootc container lint` passes | per build, plus a nightly cron | none |
| `weekly` | digest that entered nightly ≥ 7 days ago | ≥ 5 passing boots, latest boot passed, no known P1 | weekly | none |
| `stable` | digest that entered weekly ≥ 7 days ago | ≥ 5 boots, a GPU pass with `cuInit` succeeding, 5% rollout for 7 days | monthly | until next stable + 1 |

Two honest substitutions are in force until the self-hosted runners exist, and
they are visible in `GATES` rather than hidden in prose:

- **Nightly does not boot.** A hosted runner has no KVM, so nightly accepts the
  static `bootc container lint` result. That is weaker than the published
  promise, and it is why weekly still requires five real boots. Raise
  `nightly.min_boot_passes` to 1 — and delete the image-check requirement — once
  `boot-test.yml` has a runner.
- **Weekly and stable cannot promote without boot and GPU evidence.** If no
  runner produces it, the channel simply stops advancing. That is the intended
  failure: a channel that moves on missing evidence is worse than one that
  stalls.

All three are user-selectable. They must be presented by what they promise, not by
name — "weekly" means nothing to someone who has never thought about release
cadence:

| Shown as | Promise |
|----------|---------|
| Nightly | "Newest, may break. For testing." |
| Weekly | "New features weekly, small risk." |
| Stable | "New features monthly. Recommended." |

Soak time is the product's cost for stability. Publish it: "stable trails nightly
by roughly three weeks" is a sentence users can plan around.

Gates are **recorded as evidence against a digest**, not inferred. A promotion
fails if the evidence for that exact digest is missing or stale.

| Kind | Producer | Means |
|------|----------|-------|
| `build` | `build.yml` | the image built, pushed, with provenance |
| `image` | `check.yml` | `bootc container lint` passed |
| `boot` | `boot-test.yml` | the image reached multi-user in QEMU |
| `hw` | `hw-test.yml` | the driver loaded and `cuInit` succeeded on a GPU |
| `promotion` | `promote.yml` | a pointer moved to this digest |

**Soak is measured from the `promotion` record, never from the channel pointer.**
The nightly pointer moves on every commit, so "the digest nightly points at is
seven days old" is never true, and a gate written that way would deadlock weekly
promotion permanently. The first implementation of these gates did exactly that;
`test_weekly_uses_promotion_evidence_not_the_moved_pointer` is the regression
test. The same reasoning applies to stable: it asks when this digest entered
weekly, not what weekly points at now.

Evidence is a CI artefact (`.evidence/`, 90-day retention), not repository
content. Promotion runs download recent `evidence-*` artefacts from the build,
check, boot, hardware and promotion workflows, flatten them into `.evidence/`, and
evaluate. No evidence is committed, which keeps `master` a single content
lineage.

## 5. Promotion mechanism

### Repository layout

```
master
├── Containerfile
├── .github/workflows/
│   ├── build.yml        push → image → GHCR, by digest
│   ├── boot-test.yml    QEMU boot evidence
│   ├── hw-test.yml      GPU evidence
│   ├── promote.yml      gates → rewrite channels/*.json → commit → tag → release
│   └── emergency.yml    manual, two approvals, skips soak
├── channels/
│   ├── nightly.json
│   ├── weekly.json
│   └── stable.json
└── docs/
```

`channels/**` is written **only** by `promote.yml`. Branch protection and
CODEOWNERS enforce that. `build.yml` ignores the path, so a promotion cannot
trigger a build:

```yaml
on:
  push:
    branches: [master]
    paths-ignore:
      - 'channels/**'
      - 'docs/**'
```

### The channel file

A few hundred bytes, served over HTTPS, `ETag`-cached:

```json
{
  "schema": 1,
  "channel": "stable",
  "digest": "sha256:9f2c…",
  "version": "1.4.0",
  "build_id": "2026.11.10+g1a2b3c4d.r42",
  "source_commit": "1a2b3c4d…",
  "release": "v1.4.0",
  "created": "2026-11-10T00:00:00Z",
  "rollout": { "percentage": 5, "seed": "2026-11-9f2c", "started": "2026-11-10T00:00:00Z" },
  "min_source_version": "1.2.0",
  "notes_url": "https://github.com/ORG/REPO/releases/tag/v1.4.0",
  "supersedes": ["sha256:1a2b…"],
  "signature": "…"
}
```

Rules:

- The file is **signed by a key whose public half is baked into the image**.
  GitHub's immutability protects releases, not this pointer. Verification failure
  means no update, and a visible error.
- Devices pull **by digest**, not by tag. Tags are for humans and for `podman`.
- `rollout` is optional. When absent, 100%. `started` is required whenever there
  is a percentage: widening to 100% has to know when the soak began, and asking
  git for that would make CI reconstruct history the file can simply carry.
- **`supersedes` means withdrawn**, not "the digest this one replaced". The
  promotion chain lives in git; conflating the two makes every digest nightly
  ever moved past look unsafe to promote, which stops the pipeline at the first
  weekly promotion.
- `source_commit` is the build commit, so a release tag can point at the exact
  source that produced the shipped bytes without a lookup.
- The file is committed by CI and carries a signed commit. Devices still verify
  the embedded signature, because they must not trust GitHub's identity.
- The signature covers the **canonical JSON** of the document minus the signature
  field — sorted keys, no insignificant whitespace. Reformatting the file cannot
  invalidate it, and the client re-derives the payload from what it parsed.

### Promotion as a state transition

```
nightly  ──gate──>  weekly  ──gate──>  stable
   │                   │                  │
   └── channel file ───┴──────────────────┘
```

Promotion never touches the image. It rewrites one file, signs it, commits it,
tags the build commit, and publishes a release. Rollback of a promotion is
`git revert` on that file.

```
promote.yml
  1. resolve candidate digest from evidence
  2. verify gates for that exact digest
  3. rewrite channels/<channel>.json
  4. cosign sign-blob the file
  5. commit + push (signed commit)
  6. git tag -s v1.4.0 <build-sha>
  7. gh release create v1.4.0 (draft) → upload → publish
```

## 6. Client behaviour

### Channel selection

- Chosen at first boot (default: `stable`), stored in `/var/lib/aios/channel`,
  which survives deployments.
- Changing it runs `bootc switch` to the new channel's current digest and is
  effective from the next update cycle.
- The channel is never stored in the image or in `/etc`, so an update cannot
  reset a user's choice.

### Discovery and staging

```
fetch channels/<channel>.json (ETag, 5 min TTL)
  verify signature
  if digest == running digest: stop
  if digest in /var/lib/aios/bad-digests: stop
  if rollout < 100 and bucket(machine_id, seed) >= rollout: stop
  bootc switch <image>@<digest>
  after the restart, greenboot checks: compositor, agentd, GPU context
  pass -> mark deployment good
  fail -> automatic rollback, blacklist the digest locally
```

Note the verb: **`bootc switch`, not `bootc upgrade`.** Channels resolve to
digests, and bootc documents that with a digest reference `upgrade` is a no-op.
This is also why the stock `bootc-fetch-apply-updates.timer` cannot drive updates
for us and is masked in the image.

Failure to reach the channel file is not an error state. The device stays on its
current deployment and retries later. Updates are never required for the system to
work.

### Applying: the two update modes

ADR-0016 defines the user-facing choice. The command difference is small; the
policy difference is not.

Both modes stage an unlocked deployment, so the update is in place at the next
shutdown or reboot the device takes. What separates them is **who may initiate
that restart**.

| Mode | Restart initiated by | Behaviour |
|------|----------------------|-----------|
| `auto` | the system, when idle and safe | Applies at the next shutdown or reboot; may restart on its own after the predicate holds for 5 minutes |
| `on-restart` | the user only | Applies at the user's next shutdown or restart; never restarts itself |

The safety predicate, in order of importance:

```
no active unlocked user session
and no in-flight agentd task that cannot survive a restart
and (AC power or battery > 50%)
and no download in progress
```

If `auto` has not been able to restart for seven days, the shell shows one line —
"Update ready — restart when convenient" — and stops waiting. `auto` degrades to
`on-restart` rather than freezing on an always-on machine.

`--download-only` is not a mode. It is the hold behind "not now": locked for
24 hours, then unlocked. A shutdown during the hold discards the staged
deployment but keeps the cached layers, so re-staging is cheap.

`--soft-reboot=auto` is used where the target deployment does not change the
kernel. It shortens the restart; it is never offered for a driver or kernel
change, and it must be feature-detected per backend.

### Deterministic staged rollout

```python
material = machine_id.encode() + b"\x00" + seed.encode()
bucket = int.from_bytes(blake2b(material, digest_size=4).digest(), "big") % 100
eligible = bucket < rollout_percentage
```

The NUL separator matters: plain concatenation lets `ab` + `c` and `a` + `bc`
produce the same bucket, which is harmless here only by luck. blake2b is in the
standard library, which means the update client needs no crypto dependency to
answer "am I in this rollout".

No telemetry, no accounts, no server-side device registry. The same device always
makes the same decision for the same seed, and a new seed re-rolls the population.
This is the only way to stage a rollout on a system that collects nothing.

### Rollback blacklist

`greenboot` rolling back is only half the recovery. Without a blacklist, the next
update check stages the same digest again and the device boot-loops on a timer.

Two layers, because their latencies differ:

| Layer | Scope | Latency | Fixes |
|-------|-------|---------|-------|
| `/var/lib/aios/bad-digests` | one device | immediate | the device that just failed |
| channel file `supersedes` | fleet | minutes to hours | everyone else |

Neither is sufficient alone: the channel cannot know about a failing digest until
a device is withdrawn from it, and the device cannot wait for the channel before
its next check.

### Local reporting

`aios update status` shows: channel, mode, running digest, staged digest, last
failure, rollback count, and — when a restart is being withheld — the exact clause
of the safety predicate that is blocking it. This is the whole support story for
updates, and it must work offline.

## 7. GitHub Actions topology

| Workflow | Trigger | Runner | Produces |
|----------|---------|--------|----------|
| `build.yml` | push to `master`, nightly cron | hosted | OCI image, signed, pushed by digest; build evidence |
| `check.yml` | after build | hosted | `bootc container lint`; image evidence |
| `boot-test.yml` | after build | self-hosted with KVM | boot evidence (`KVM_RUNNER=true`) |
| `hw-test.yml` | after build | self-hosted with GPU | driver + `cuInit` evidence (`GPU_RUNNER=true`) |
| `promote.yml` | after build, schedule, manual | hosted | channel file commit, signed tag, release |

There is no separate `emergency.yml`. The emergency lane is an input to
`promote.yml` — it skips soak, still requires the hardware gate, and records two
approvers in the promotion commit. One workflow that can write the pointer is
easier to protect than two.

The self-hosted jobs are gated on repository variables rather than left to queue
forever. An unset variable produces a skipped job, which is honest; a missing
runner produces a queued job nobody notices. Self-hosted runners attached to a
public repository are also a security boundary: only run them where untrusted
pull requests cannot reach the runner.

Sketch of the core build:

```yaml
name: build
on:
  push:
    branches: [master]
    paths-ignore: ['channels/**', 'docs/**']
  schedule: [{ cron: "0 2 * * *" }]
  workflow_dispatch:

jobs:
  image:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
      id-token: write
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/build-push-action@v6
        id: build
        with:
          context: .
          push: true
          provenance: true
          sbom: true
          tags: |
            ghcr.io/ORG/aios:sha-${{ github.sha }}
          labels: |
            org.opencontainers.image.revision=${{ github.sha }}
            aios.build.id=${{ github.run_id }}
      - name: sign
        run: cosign sign --key env://COSIGN_KEY ghcr.io/ORG/aios@${{ steps.build.outputs.digest }}
      - name: record digest
        run: echo "${{ steps.build.outputs.digest }}" >> "$GITHUB_STEP_SUMMARY"
```

Notes that matter:

- **Published by digest.** The `sha-` tag is a convenience; the digest is the
  identity. There is no moving `nightly` tag to depend on.
- **`provenance` and `sbom`** are cheap and make the supply chain legible.
- **Signing key in a KMS or secret, not on a runner filesystem.** The public half
  ships in the image.
- **The installer ISO is not built on every commit.** `bootc-image-builder` is
  slow and disk-hungry. Build it for `stable` promotions and on demand, and attach
  it to the release.

### Retention

| What | Kept |
|------|------|
| nightly digests | 30 |
| weekly digests | 12 |
| stable digests | all |
| release assets (ISO, SBOM) | all |

Without a retention policy, GHCR storage and release assets become a silent bill.
Prune by age, and never prune the digest a channel currently points at.

## 8. Releases and tags

Each promotion produces one immutable GitHub Release. This is the human record and
the provenance anchor; it is **not** what devices poll.

```bash
gh release create v1.4.0 \
  --draft \
  --target "$BUILD_SHA" \
  --notes-file notes/v1.4.0.md

gh release upload v1.4.0 dist/aios-1.4.0.iso dist/sbom.json
gh release edit v1.4.0 --draft=false      # publish → tag and assets lock
gh release verify v1.4.0                  # immutability + attestation
```

Why the draft-then-publish order is mandatory: immutability engages on
publication. Assets uploaded after publish are impossible, so the release must be
assembled completely before it goes live.

What this buys, for no infrastructure:

- The tag is pinned to the build commit and cannot be moved.
- Assets (ISO, SBOM, signatures) cannot be replaced or deleted.
- GitHub generates a release attestation recording tag, commit and assets.
- Users get readable notes and a download page.

What it does not buy:

- **Immutability is not authenticity.** It proves the release has not changed since
  publication; it says nothing about whether it was good. Our own signature on the
  image and the channel file is still required.
- **A deleted immutable release's tag name cannot be reused.** Choose version
  numbers with that in mind; a yanked version stays yanked.

## 9. Emergency security lane

```
CVE discovered
  -> fix lands on master
  -> nightly build + boot test (minutes)
  -> expedited promotion: skip soak, require two approvals
  -> channel file updated
  -> optional forced rollout for known-vulnerable devices
```

- The lane bypasses soak, not the hardware gate. Skipping the boot test is how an
  emergency becomes an outage.
- Every use is logged publicly with the reason and the approvers.
- If the lane is used more than roughly once a quarter, the cadence is wrong.

## 10. Channel switching and state compatibility

`/var` persists across deployments and across channel switches. That creates a
one-directional constraint:

- **Forward within a lineage** (stable to weekly, weekly to nightly): the state is
  older than the OS expects. Supported.
- **Backward** (nightly to stable): the state may be newer than the OS expects.
  Supported with a warning, and only if no migration has been applied that the
  older image does not understand.
- **Migrations are forward-only.** Any schema change in `/var/lib/aios` must be
  additive, or it must record a floor version that blocks downgrade.

Document this in the UI as a sentence, not a table: "Switching to a slower channel
keeps your data. Switching back afterwards may require reinstalling."

## 11. What cannot be fully automated

**The hardware gate.** GitHub-hosted runners have no GPU, so they cannot validate
the NVIDIA driver, and therefore cannot validate the one thing most likely to
break. If a change regresses the module, a hosted runner will happily build and
sign a broken image.

Two honest options:

1. **Self-hosted runner with a GPU** in a machine you control. Preferred; makes
   the gate real.
2. **Manual sign-off on a reference machine** before promotion. Slower, but
   honest, and better than a green check that means nothing.

Running the boot test also needs KVM. Confirm `/dev/kvm` availability on the hosted
runner; if it is absent, the boot gate moves to the self-hosted runner too.

"Completely automated" is achievable for build, sign, promote and rollout. It is
not achievable for "this works on a real GPU" without hardware. Say so now rather
than discovering it when a release ships broken.

## 12. Failure modes

| Failure | Symptom | Mitigation |
|---------|---------|------------|
| GitHub unavailable | No updates; devices stay functional | Long cache TTL; devices retry; keep working offline |
| `raw.githubusercontent.com` rate limit | Some fleets stop resolving after 5000 req/IP/hour | Move the channel URL onto a domain we control and CDN it |
| Rolled-back digest re-staged | Device appears to recover, then breaks again hours later | Mask `bootc-fetch-apply-updates.timer`; per-device `bad-digests`; channel `supersedes` |
| Bad digest promoted | Broken devices | Rollout percentage + `supersedes` + per-device rollback |
| `channels/**` compromised | Attacker redirects every device | Branch protection; CODEOWNERS; code signing; embedded signature check |
| Signing key leaked | Attacker can sign a malicious channel file | KMS-held key; rotation plan; revoke via new key shipped in a release |
| Registry garbage-collects a live digest | Updates fail for everyone on that channel | Never prune a referenced digest; verify before prune |
| Soak skipped under pressure | Regression reaches stable | Emergency lane requires two approvals and a public log |
| Version assigned twice | Two digests claim `1.4.0` | Promotion assigns atomically; a published release's tag cannot move |
| Channel switch loses user data | Trust destroyed | Migrations additive and forward-only; warning before downgrade |

## 13. Open questions

- The final channel URL, and when to front it with our own domain.
- Soak durations per gate. `weekly` is user-facing, so its soak must be long
  enough to mean something rather than being a nightly with a different name.
- Image and release-asset retention numbers versus storage cost.
- Whether to support offline update media for air-gapped devices.
- Whether `RELEASE_TOKEN` is a fine-grained PAT or a GitHub App. The former is
  quick and ties the pipeline to one person; the latter is the right answer and
  needs an app installation first.

## 14. Implementation status (2026-11-10)

**Built and tested**

- `tools/release/` — gates, candidate selection, promotion, widening,
  withdrawal, canonical signing payload, device-side resolution, and a
  four-week simulation. The suite lives in `tests/release/`
  ([ADR-0017](../adr/0017-tests-live-in-tests.md)) and has 158 tests, all
  passing.
- `Containerfile` — pinned base, NVIDIA kmod built against the image's own
  kernel and stripped, session libraries, greenboot checks, stock timer masked.
- `ci/promote.sh` and the five workflows — build, static check, boot, hardware,
  promotion.
- `channels/` with the contract documented and no fabricated pointers.

**Not verified, deliberately**

- `ci/boot-test.sh` and `ci/hw-test.sh` have never run: there is no KVM or GPU
  runner. They are marked unverified in the files themselves.
- No image has been built by this repository's CI. The NVIDIA build step *was*
  executed against the pinned base image on 2026-11-10 and produced
  `kmod-nvidia-7.3.3-300.fc45…` plus a surviving `nvidia.ko.xz` after the
  toolchain was removed. The rest of the Containerfile is unexercised.
- No cosign key exists. The HMAC signer is a local stub and must never ship.

**Facts that corrected earlier sections, found by running things**

- greenboot is **not** installed in `fedora-bootc:45`; it is a separate package.
- `bootc-fetch-apply-updates.timer` is **enabled** in the base image, which
  confirms ADR-0016 §5 as a real default rather than a theoretical risk.
- The base image kernel lags Fedora updates (7.2.15 in the image, 7.3.3 in
  updates), so `kernel-devel-matched` upgrades the kernel. The module build must
  read the kernel version *after* installing, or it fails against headers that no
  longer exist.
- All 14 session-runtime packages named in the Containerfile resolve for Fedora
  45, and RPMFusion has both `free` and `nonfree` repositories for 45.
