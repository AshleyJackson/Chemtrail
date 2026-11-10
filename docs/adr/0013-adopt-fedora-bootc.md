# ADR-0013: Adopt Fedora bootc as the base platform

- **Status:** Accepted
- **Date:** 2026-11-10
- **Deciders:** project owner
- **Supersedes:** ADR-0004 (mechanism)
- **Superseded by:** —
- **Resolves:** the deferred base decision in ADR-0009

## Context

ADR-0009 reopened the base and set out eight must-haves implied by the current
product definition (assistant-first shell, local-first inference, public
distribution, NVIDIA required). It recommended Fedora bootc as the default if a
base had to be selected now, pending measurement.

The product owner has elected to settle it immediately rather than run the
two-week comparison. That is a defensible call: the comparison's purpose was to
test whether Alpine's smallness could justify its gaps, and the answer was
already clear enough to act on — Alpine scored 1.5 of 8 on must-haves while
winning only the three lowest-weighted criteria.

Fedora bootc is the only candidate that passes all eight without custom
infrastructure:

- **NVIDIA module lifecycle (M1, M2).** The kernel and its modules ship inside
  the same image. There is no drift window to manage, because a kernel update and
  a driver rebuild are the same artefact.
- **Secure Boot (M3).** Fedora's shim is signed; MOK enrolment is a shipped,
  documented flow.
- **Installer (M4).** `bootc-image-builder` produces an Anaconda-based
  installable ISO, and Anaconda is a graphical installer that already works.
- **Atomic updates and rollback (M5).** ostree deployments, with `greenboot`
  providing health-checked automatic rollback.
- **Extensible compositor stack (M6).** Current Mesa, Wayland and kernel.
- **Reproducible image build (M7).** The OS *is* a container image. The build
  pipeline is a Containerfile.
- **Supportable update channel (M8).** `bootc upgrade` against a registry we
  control.

Full comparison in [base-selection.md](../architecture/base-selection.md).

## Decision

Adopt **Fedora bootc** as the base platform.

1. **The OS is an OCI image.** Built with a Containerfile from
   `quay.io/fedora/fedora-bootc`, targeting `x86_64` and UEFI only for v1.
2. **Built with `bootc-image-builder`** to produce the installable ISO and the
   disk images. Do not fork Anaconda.
3. **Pinned by digest.** The base image, RPMFusion content, and any third-party
   repositories are pinned. A rebuild is a deliberate act, not a rolling pull.
4. **`greenboot` is the health and rollback mechanism.** Required checks verify
   that the compositor started and `agentd` answered its socket. Failure rolls
   back the deployment unaided.
5. **Do not ship a desktop environment.** The base carries only the runtime the
   shell needs: Mesa, Wayland, PipeWire, NetworkManager, portals, fonts. The
   shell is ours (ADR-0010).
6. **SELinux stays enforcing.** Write policy for our daemons rather than
   disabling it; a permissive system undermines the argument for owning the
   compositor.
7. **Do not build on ublue/Bazzite.** Their images are excellent references and
   their NVIDIA patterns should be copied, but basing on them inherits a desktop
   and a package set we would have to remove. Take the recipes, not the image.

Implementation detail in [fedora-bootc.md](../architecture/fedora-bootc.md).

## Consequences

### Positive

- **The project's hardest constraint disappears.** CUDA, PyTorch, vLLM, TensorRT
  and the entire accelerator ecosystem work natively on glibc. This is a larger
  win than the base decision itself —
  [ADR-0014](0014-nvidia-and-workloads-on-glibc.md) records the simplification.
- Four must-haves (installer, Secure Boot, atomic rollback, driver lifecycle) are
  inherited solved rather than built.
- The build pipeline is a container build, which is the tooling most contributors
  already have.
- Release engineering reduces to: build image, sign, push, tag.
- If the shell succeeds, there is no second platform migration waiting.

### Negative / costs

- **The base is 1.2–1.5 GB installed and carries systemd.** We give up the
  smallness argument permanently. It was worth less than it cost, but it was real.
- Fedora's release cadence and packaging decisions are now constraints on us. A
  regression upstream becomes our regression.
- bootc is still maturing. Its interfaces have changed before and will again; we
  will absorb that churn.
- Kernel-update density is higher than a pinned appliance image, so our test
  cadence must match Fedora's or users receive combinations we never tested.
- selinux policy authoring for `agentd` and the shell is real, unglamorous work
  with no natural completion.
- We are, and will remain, "a Fedora derivative". Any positioning that depends on
  technical novelty at the OS layer is now unavailable.
- Accessibility is inherited from the platform better than on Alpine, but our own
  shell still carries the burden (ADR-0010).

### Neutral / follow-on

- The Alpine architecture work is retained as the documented appliance SKU
  (ADR-0009 §6.3), with its original justification (known hardware, instant-on)
  rather than the generic one.
- ADR-0004's requirements survive; its mechanism is replaced by ostree
  generations, so it is superseded rather than deleted.

## Alternatives considered

**NixOS.** The strongest technical alternative: better reproducibility and
rollback than bootc, and a cleaner declarative model. Rejected on contributor
familiarity and because its installer and desktop-integration story is weaker for
a consumer product. Worth revisiting if bootc's churn becomes unmanageable.

**Debian with a custom atomic layer.** Rejected because "custom atomic layer" is
the entire cost we are trying to avoid. Debian would need us to build the update
and rollback mechanism that bootc provides.

**Arch.** Rejected for a public product. Excellent for an expert's machine,
unsupportable for strangers.

**Alpine appliance only.** Rejected for this product, retained as an SKU. It
would ship sooner but requires selling hardware.

**Ubuntu.** Rejected. No comparable immutable model outside snaps, and the
desktop integration is Canonical-controlled.

**Run the two-week comparison first anyway.** Rejected by the product owner. The
decision record notes the trade honestly: we accepted a small risk of being wrong
in exchange for two weeks of schedule, and the must-have matrix suggests the risk
was low.

## Follow-ups

- Write the Containerfile and produce a first bootable image. This is the next
  concrete deliverable.
- Choose the Fedora release to track and the rebuild cadence.
- Implement `greenboot` checks for compositor and `agentd`.
- Decide the MOK key strategy: build-time key shared across devices versus
  per-device generation. See [fedora-bootc.md](../architecture/fedora-bootc.md#secure-boot-and-mok).
- Author SELinux policy for `agentd` and the shell.
- Define the registry, signing, and promotion model.
- Update ADR-0009's status to record that the deferred decision is resolved.
- Keep the measurement plan from
  [base-selection.md §8](../architecture/base-selection.md#8-how-to-settle-this-with-evidence)
  as a regression check: if bootc's base turns out to cost more than predicted in
  boot time or memory, that is evidence, not an argument.
