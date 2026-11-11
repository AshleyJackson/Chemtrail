# AI_OS

An assistant-first operating system: the user states intent, the system acts, and
applications are windows rather than the primary interface.

**Status:** scaffold implemented. Base platform settled as **Fedora bootc**; the
release pipeline exists as code and runs end to end on dummy digests. The install
path is a network install ([ADR-0020](adr/0020-thin-install-media.md), accepted):
Fedora's own netinst media plus a hosted kickstart that pulls the image from
GitHub Container Registry — no installer ISO is built or published, because the
first one came out at 3.42 GB against GitHub's 2 GiB per-asset limit. The desktop
is COSMIC (ADR-0018) but is not in the image yet. The build workflow publishes an
image to GHCR on every commit to `master`; it has now published, and the hosted
kickstart pins that first image by digest. What it took to get there — three
workflow bugs and a re-pinned base — is recorded in the changelog below.

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
2. [ADR-0018](adr/0018-cosmic-desktop-for-v1.md) — COSMIC is the desktop, and the
   assistant is the surface above it. [ADR-0010](adr/0010-assistant-first-shell.md)
   argued the opposite and is superseded; read it for the trade-off, not the plan.
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

## Running it

- [Installing the image in VirtualBox](run/virtualbox.md) — build the network-install
  medium, install it in a VM, and check that the installed system boots and reports
  its own build identity.

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
| [0010](adr/0010-assistant-first-shell.md) | Assistant-first shell is the interface | Superseded by 0018 |
| [0011](adr/0011-local-first-cloud-optional.md) | Local-first inference, cloud optional | **Accepted** |
| [0012](adr/0012-public-product-scope.md) | Public product scope | **Accepted** |
| [0013](adr/0013-adopt-fedora-bootc.md) | Adopt Fedora bootc as the base | **Accepted** |
| [0014](adr/0014-nvidia-and-workloads-on-glibc.md) | NVIDIA, CUDA, and workload packaging | **Accepted** |
| [0015](adr/0015-release-channels-by-promotion.md) | Release channels by promotion, not branch merging | **Accepted** — revised 2026-11-10 |
| [0016](adr/0016-update-application-policy.md) | Update application policy: two modes, no forced reboots | **Accepted** |
| [0017](adr/0017-tests-live-in-tests.md) | Tests live in `tests/`, and everything has a test | **Accepted** |
| [0018](adr/0018-cosmic-desktop-for-v1.md) | Ship COSMIC as the desktop environment for v1 | **Accepted** |
| [0019](adr/0019-no-xlibre.md) | Do not ship XLibre, in any role | Rejected |
| [0020](adr/0020-thin-install-media.md) | Thin install media, capabilities provisioned after first boot | **Accepted** — 2026-11-11 |

Five ADRs define the product: inference is local-first with an explicit cloud
route (0011), distribution is public (0012), the platform is Fedora bootc (0013),
and releases are promoted by digest (0015) with a user-chosen restart policy
(0016). The interface is recorded separately: ADR-0018 makes COSMIC the desktop
and the assistant a layer-shell surface above it, superseding ADR-0010's
commitment to a compositor we write. ADR-0014 records what the base change
dissolved. ADR-0017 is process rather than product: it fixes where tests live and
makes "everything has a test" a failing assertion instead of an intention.
ADR-0019 is a rejection rather than a commitment: XLibre is out of the image, and
Fedora's Xwayland stays the only X server. ADR-0020 decides how the system reaches
a machine rather than what it contains: nightlies publish an image and not an
installer, the install medium carries no payload (Fedora's netinst plus a hosted
kickstart), and the NVIDIA layer arrives after first boot.

## Changelog of the documentation

**2026-11-11, fifteenth revision.** The first image was published to GHCR, and the kickstart now points at it.

- **The build workflow needed two more fixes before it could publish.** First:
  buildx looks for a `Dockerfile` by default, but this repository's build file is
  named `Containerfile`, so every CI build died before building anything. Second:
  the pinned base digest no longer resolved on quay.io — Fedora re-tags `45` at
  point releases and quay garbage-collects manifests that no tag references, so a
  digest pin there is a lease, not an anchor (now noted in the Containerfile). The
  base was re-pinned to the current index digest of `fedora-bootc:45`, verified
  resolvable by digest before pushing.
- **The first image is published and anonymously pullable.** CI built from commit
  9219567 and pushed it to `ghcr.io/ashleyjackson/chemtrail`; an anonymous token
  fetches its manifest, which is what Anaconda in a fresh VM will do. The package
  is public because the repository is public — no extra step was needed, but it
  was checked rather than assumed.
- **The hosted kickstart exists and validates.** `install/aios-netinst.ks` pins
  that image by digest (the multi-arch index digest CI records and signs), sets
  storage/locale/root password, and parses cleanly under pykickstart 3.77-1.fc45
  with both `bootc` options recorded — source with its `registry:` transport
  prefix, target without one, as this release requires.
- **The VM recipe was corrected before running it.** The Fedora download URL in
  the docs did not exist (the real one is on `/server/download`, under
  `download.fedoraproject.org/pub/...`), and the VirtualBox command for a NAT
  network was invented (`createnatnet`); 7.x uses `natnetwork add`, and a NIC set
  to `natnetwork` must name its network or it silently gets the default.

**2026-11-11, fourteenth revision.** ADR-0020 accepted; the install path becomes a network install.

- **ADR-0020 accepted** (the owner: "i accept the thin client"). Nightlies publish
  an image and never an installer; the install medium is Fedora's own netinst plus
  a hosted kickstart that pulls the image from GHCR with Anaconda's `bootc` command.
- **The F45 claim was verified, not assumed.** The announcement behind ADR-0020
  demonstrated Rawhide media only, so before accepting it I checked the release we
  track: pykickstart 3.77-1.fc45 from the Fedora 45 repositories — the parser
  Anaconda on F45 media uses — registers `bootc` (`F45_Bootc`) and parses
  `--source-imgref`/`--target-imgref` without error, recording both options. The
  ADR now records that evidence and the full option set of this release, including
  that `--target-imgref` takes no transport prefix and must be set explicitly for
  updates to work at all.
- **The build workflow had never published an image, and why is now known.** It
  failed on its first run: GHCR package names must be lowercase, but the tag was
  built from `github.repository`, which is mixed case. The workflow now computes a
  lowercased registry reference; this revision's push is the first real attempt to
  publish an image to GHCR.
- **The network-install path lands in [run/virtualbox.md](run/virtualbox.md):**
  Fedora's netinst, `inst.ks=` on the kernel command line, and a kickstart served
  over HTTP. The hosted kickstart itself is written once CI has published an image
  to pin it to; until then there is nothing for it to point at.

**2026-11-10, thirteenth revision.** The installer turned out to be unpublishable.

- **The ISO is 3.42 GB and GitHub caps a release asset at 2 GiB.** The nightly
  artefact could not have been uploaded at any cost, which reframes the size
  question from budget to feasibility.
- **Measured what the builder can actually produce.** `anaconda-iso` and `iso`
  both come out at exactly 3,419,379,712 bytes, so the second is not a thin
  installer; `bootc-installer` fails with `bootc container inspect: exit status 1`
  and prints nothing more at debug level, although the same command works when run
  in the image directly. There is no small ISO in this release of the tool.
- **Measured where the payload goes.** NVIDIA is ~1.19 GB of the 3.5 GB the build
  adds to the base and graphics is ~0.39 GB, so two thirds of the payload is
  driver and rendering.
- **ADR-0020 proposed**, not accepted: nightlies publish an image rather than an
  installer, the medium carries no payload and pulls the image from a registry with
  Anaconda's `bootc` kickstart command, and the NVIDIA layer is a second image that
  `aios-provision` fetches after first boot on machines that have the hardware.
- **The reason the split is driver-first rather than desktop-first** is recorded
  there: the assistant is a layer-shell overlay and needs a compositor, so a base
  without COSMIC has no product, while a base without NVIDIA merely runs on
  `llvmpipe` until the layer arrives.

**2026-11-10, twelfth revision.** The image became installable.

- **`ci/build-iso.sh` builds an installer ISO** from the platform image with
  `bootc-image-builder`, using a throwaway registry rather than podman's storage,
  so it runs under Docker and Docker Desktop as well as podman.
- **The image now copies its repository definitions into `/etc/yum.repos.d`.**
  Fedora 45 moved them to `/usr/share/dnf5/repos.d`, and osbuild reads only the
  old location, so the ISO build failed with `NoReposError` until the files were
  where the builder looks. dnf5 reads both, so nothing else changes.
- **An ISO was built and installed in VirtualBox** (EFI firmware, interactive
  Anaconda), and the installer wrote the container payload to disk. The first boot
  of the installed system is the next check, not a claim this revision makes;
  [run/virtualbox.md](run/virtualbox.md) records the recipe and the three failures
  that shaped it.
- The image is still the platform only. COSMIC is not in it, so this proves the
  install and boot path, not the product.

**2026-11-10, eleventh revision.** XLibre rejected.

- **ADR-0019 rejected.** XLibre was evaluated in both roles it could occupy and
  dropped. It carries no Xwayland, so it cannot serve the COSMIC session, and its
  driver ABI (videodrv 28, xinput 26) cannot load Fedora's drivers, including the
  NVIDIA driver this OS exists to run (ABI 25.2).
- **The decision is the measurement.** It builds on Fedora 45 — that was checked
  by building it to completion — so the objection is the ABI wall and the missing
  Wayland server, not whether the fork compiles.
- **The X11 path is Fedora's Xwayland inside COSMIC**, and v1 has no legacy X11
  session. If one is ever needed, the candidate is Fedora's Xorg, which shares the
  driver's ABI; XLibre is not the fallback.
- An in-progress `ci/build-xlibre.sh` was deleted rather than committed disabled.

**2026-11-10, tenth revision.** COSMIC becomes the desktop.

- **ADR-0018 accepted, superseding ADR-0010.** The session is COSMIC, installed
  from Fedora 45 packages, and the assistant becomes a layer-shell overlay
  summoned by a global shortcut rather than the session itself.
- The trade-off is stated in the ADR rather than hidden: the assistant is now
  ignorable, and the product's face is COSMIC's. What it buys is months off the
  critical path, an inherited accessibility baseline, and a desktop that already
  works while the loop is being built.
- Verified before deciding: Fedora 45 ships COSMIC 1.10.0 including
  `cosmic-session` and `cosmic-comp`; `cosmic-comp` carries layer-shell and
  foreign-toplevel interfaces; `cosmic-greeter` needs `greetd`, which the image
  does not have yet.
- The compositor spike becomes a COSMIC integration spike; Phase 2 loses the
  compositor and gains session integration.
- ADR-0006 is revived: the layer-shell assistant surface it proposed is now the
  mechanism the product depends on.

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
| Channel URL (it also hosts the install kickstart for `inst.ks=`), and when to front GitHub with our own domain | Update resolution; network install | — |
| Deferral ceiling and escalation for security updates | ADR-0016 follow-up | — |
| Does a COSMIC layer-shell overlay hold focus and summon over fullscreen, at under 50 ms? | Assistant surface v0 | — |
| COSMIC app set and first-run experience | Public beta | — |
| Interaction model: how much does the shell take over | Phase 1 prototype | — |
| Fedora release to track and rebuild cadence | Image pipeline | — |
| MOK key strategy: build-time shared key vs per-device | First-run UX | — |
| SELinux policy scope for `agentd` and the shell | Any public release | — |
| Minimum local model and recommended VRAM | ADR-0014 follow-up | — |
| Accessibility approach for a from-scratch shell | Any public release | — |
| Registry hosting, signing, and promotion | Update channel | — |
| Funding and staffing for a public product | ADR-0012 follow-up | — |
| Whether the Alpine appliance SKU is in scope for year one | ADR-0009 follow-up | — |
