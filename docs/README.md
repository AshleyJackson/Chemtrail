# AI_OS

An assistant-first operating system: the user states intent, the system acts, and
applications are windows rather than the primary interface.

**Status:** scaffold implemented. Base platform settled as **Fedora bootc**; the
release pipeline exists as code and runs end to end on dummy digests. No
compositor, no shell, and no published image yet.

## What this project is

Not a distribution. The differentiator is the **loop** — perceive context, decide
with a model, act on the machine, converse — delivered through a shell we own. The
OS is the host for that shell.

The OS layer is deliberately boring: Fedora bootc gives atomic image updates,
rollback, Secure Boot, an installer, and working NVIDIA. None of that is
differentiated, and none of it should consume the project.

## Reading order

1. [Fedora bootc platform](architecture/fedora-bootc.md) — how the OS is built,
   updated, signed, and installed.
2. [ADR-0010](adr/0010-assistant-first-shell.md) — the shell is the product.
3. [AI runtime](architecture/ai-runtime.md) — control plane, model store, routing,
   tool execution.
4. [ADR-0014](adr/0014-nvidia-and-workloads-on-glibc.md) — GPU and workload
   packaging, now that libc is not an obstacle.
5. [Release engineering](architecture/release-engineering.md) — channels,
   promotion by digest, and why there is no branch merging.
6. [ADR-0016](adr/0016-update-application-policy.md) — automatic versus
   on-restart updates, and why "no reboot" is not a thing we can sell.
7. [Roadmap](roadmap.md) — ordered by risk retired, not by component.
8. [Base selection](architecture/base-selection.md) — why the base changed. Read
   for the reasoning, not the plan.
9. [Architecture overview](architecture/overview.md) — full component map.
10. [NVIDIA acceleration](architecture/nvidia.md) and
    [image and updates](architecture/image-and-updates.md) — historical analyses
    retained for their reasoning; their mechanisms are superseded.

## Decision log

| ID | Title | Status |
|----|-------|--------|
| [0001](adr/0001-alpine-musl-base.md) | Adopt Alpine Linux + musl as the base | Superseded by 0009 |
| [0002](adr/0002-nvidia-acceleration-strategy.md) | NVIDIA acceleration strategy | Superseded by 0014 |
| [0003](adr/0003-podman-workload-isolation.md) | Isolate AI workloads in Podman | Superseded by 0014 |
| [0004](adr/0004-immutable-ab-updates.md) | Immutable image with A/B updates | Superseded by 0013 |
| [0005](adr/0005-plasma-desktop.md) | KDE Plasma 6 as the desktop | Superseded by 0010 |
| [0006](adr/0006-layer-shell-assistant.md) | Assistant as a standalone surface | Proposed — narrowed |
| [0007](adr/0007-model-store.md) | Content-addressed model store | Proposed |
| [0008](adr/0008-tool-sandbox.md) | Sandbox tool execution with bwrap + seccomp | Proposed |
| [0009](adr/0009-reopen-base-selection.md) | Reopen the base platform decision | Accepted — resolved by 0013 |
| [0010](adr/0010-assistant-first-shell.md) | Assistant-first shell is the interface | **Accepted** |
| [0011](adr/0011-local-first-cloud-optional.md) | Local-first inference, cloud optional | **Accepted** |
| [0012](adr/0012-public-product-scope.md) | Public product scope | **Accepted** |
| [0013](adr/0013-adopt-fedora-bootc.md) | Adopt Fedora bootc as the base | **Accepted** |
| [0014](adr/0014-nvidia-and-workloads-on-glibc.md) | NVIDIA, CUDA, and workload packaging | **Accepted** |
| [0015](adr/0015-release-channels-by-promotion.md) | Release channels by promotion, not branch merging | **Accepted** — revised 2026-11-10 |
| [0016](adr/0016-update-application-policy.md) | Update application policy: two modes, no forced reboots | **Accepted** |
| [0017](adr/0017-tests-live-in-tests.md) | Tests live in `tests/`, and everything has a test | **Accepted** |

Six ADRs define the product: the shell is the interface (0010), inference is
local-first with an explicit cloud route (0011), distribution is public (0012),
the platform is Fedora bootc (0013), and releases are promoted by digest (0015)
with a user-chosen restart policy (0016). ADR-0014 records what the base change
dissolved. ADR-0017 is process rather than product: it fixes where tests live and
makes "everything has a test" a failing assertion instead of an intention.

## Changelog of the documentation

**2026-11-10, ninth revision.** Tests moved to `tests/`, and the rule has teeth.

- **ADR-0017 accepted.** All tests live in a top-level `tests/` tree mirroring
  `tools/`, and nothing named `test_*` lives anywhere else.
  `tools/release/tests/` is gone; the discovery command no longer names a tool.
- **"Everything has a test" is enforced rather than intended.**
  `tests/layout/test_layout.py` walks the tree and fails with a list of modules
  that have no `test_<module>.py`. Writing the rule exposed four modules with
  only indirect coverage — `canonical`, `signing`, `evidence` and `demo` — each
  of which now has its own test module.
- **The documentation is tested too.** Relative links resolve, every document is
  reachable from this index, ADR numbers are sequential, every ADR carries the
  template sections and a known status, and every ADR appears in the decision
  log.
- The suite grew from 89 to 158 tests. One command runs all of it:
  `PYTHONPATH=tools/release python -m unittest discover -s tests -t .`
- `tests.yml` runs that command, `bash -n` over every `ci/*.sh`, and
  `ci/validate-workflows.py`, on push and on pull request.

**2026-11-10, eighth revision.** The release design became code.

- `tools/release/` implements the gates, selection, promotion, widening,
  withdrawal, canonical signing payload, and device-side resolution. 89 tests.
- **Soak is measured from a recorded promotion, not from the channel pointer.**
  The first implementation deadlocked weekly behind the always-moving nightly
  pointer; the regression test and the reasoning are in
  [release-engineering.md](architecture/release-engineering.md) §4.
- **`supersedes` means withdrawn**, not "the previous digest". Conflating them
  made every digest nightly had moved past look unsafe to promote.
- The Containerfile builds the NVIDIA module against the image's own kernel and
  strips the toolchain. Two upstream facts were wrong in these docs and are
  corrected: greenboot is not in the base image, and the stock update timer is
  enabled by default.
- Nightly currently accepts `bootc container lint` instead of a real boot,
  because a hosted runner has no KVM. Weekly still requires boots, so the weaker
  gate cannot leak into a slower channel.

**2026-11-10, seventh revision.** Channel storage and branch model revised.

- **One branch: `master`.** The long-support lineage is dropped for v1; ADR-0015
  records the reversal and its cost rather than editing the sixth revision away.
- **Channels are signed JSON files in `channels/` on `master`**, not a hosted
  manifest service. `git log` becomes the promotion audit trail.
- **GitHub Releases and tags** carry the human-facing record: immutable releases
  with the tag pinned to the build commit, assets and an attestation. They are not
  the update pointer, because a release cannot answer "what is stable now".
- `release-engineering.md` rewritten for the file-based pointer, the release
  workflow, and the GitHub availability and rate-limit risks.
- **ADR-0015 accepted** in this form.
- **ADR-0016 accepted** in this form.

**2026-11-10, sixth revision.** Three questions answered.

- The long-support channel is named **`extended`**, not LTS: no feature changes,
  security fixes only, roughly 12–13 months, bounded by Fedora's own support
  window. ADR-0015 records the resolution.
- `weekly` is **user-facing**, so all four channels are selectable. Channels are
  presented by promise rather than by name.
- The default update mode is **automatic** (ADR-0016).

*The `extended` channel and the four-channel count were both reversed in the
seventh revision; this entry is retained as the record of what was decided at the
time.*

**2026-11-10, fifth revision.** Update application policy.

- ADR-0016 defines the two user-facing modes, automatic and on-restart, and
  records that neither can mean "no restart".
- Corrected the update mechanism: channels resolve to digests, so every update is
  `bootc switch` and `bootc upgrade` is a no-op.
- Found and designed out a bootc failure mode: the stock
  `bootc-fetch-apply-updates.timer` re-applies a rolled-back digest within hours.
  It is masked, and rolled-back digests are blacklisted per device.
- [release-engineering.md](architecture/release-engineering.md) now covers the
  safety predicate, the two modes, and the rollback blacklist.

**2026-11-10, fourth revision.** Release channels designed.

- ADR-0015 proposes promotion by digest over branch merging, with the
  long-support channel as the one genuine branch. (Since superseded: see the
  seventh revision.)
- New [release-engineering.md](architecture/release-engineering.md) specifies the
  pipeline, manifest format, gates, and GitHub Actions topology.

**2026-11-10, third revision.** Fedora bootc selected.

- ADR-0013 adopted the base and superseded the A/B mechanism (0004).
- ADR-0014 recorded that CUDA, PyTorch and native workloads now work, superseding
  the staged FOSS-first strategy (0002) and mandatory containerisation (0003).
- New [fedora-bootc.md](architecture/fedora-bootc.md) replaces the Alpine image
  mechanism.
- [nvidia.md](architecture/nvidia.md) and
  [image-and-updates.md](architecture/image-and-updates.md) are retained as
  historical reasoning, clearly marked.

**2026-11-10, second revision.** Product answers changed the premises:
assistant-first shell (0010, superseding 0005), public product (0012), local-first
with cloud fallback (0011), and the base reopened (0009).

**2026-11-10, first revision.** Initial architecture and ADR-0001 through 0008.

## Conventions

- Decisions are ADRs and are immutable once accepted. To change one, supersede it.
- ADR status values, numbering and the template: [adr/README.md](adr/README.md).
- Tests live in `tests/`, mirroring the tool they cover, and every module has one
  ([ADR-0017](adr/0017-tests-live-in-tests.md)). The suite is standard-library
  `unittest`, so nothing has to be installed to run it.
- `docs/architecture/` describes how the system works; `docs/adr/` describes why.
- Superseded documents stay in the tree. The record of a decision that turned out
  to be conditional is more useful than a tidy tree.
- Claims about upstream projects carry an observation date.
- Every ADR has a `Follow-ups` section.

## Open questions

| Question | Blocks | Owner |
|----------|--------|-------|
| Self-hosted GPU runner for the hardware gate | Any automated promotion to stable | — |
| Self-hosted KVM runner for the boot gate | Any automated promotion to weekly | — |
| `RELEASE_TOKEN` with permission to push to `channels/**` | Any automated promotion | — |
| Channel URL, and when to front GitHub with our own domain | Update resolution | — |
| Deferral ceiling and escalation for security updates | ADR-0016 follow-up | — |
| Compositor: build on `wlroots`, fork Sway/niri, or `Smithay` | Shell v0 | — |
| Interaction model: how much does the shell take over | Phase 1 prototype | — |
| Fedora release to track and rebuild cadence | Image pipeline | — |
| MOK key strategy: build-time shared key vs per-device | First-run UX | — |
| SELinux policy scope for `agentd` and the shell | Any public release | — |
| Minimum local model and recommended VRAM | ADR-0014 follow-up | — |
| Accessibility approach for a from-scratch shell | Any public release | — |
| Registry hosting, signing, and promotion | Update channel | — |
| Funding and staffing for a public product | ADR-0012 follow-up | — |
| Whether the Alpine appliance SKU is in scope for year one | ADR-0009 follow-up | — |
