# syntax=docker/dockerfile:1

# AI_OS platform image (Phase 0).
#
# Deliberately thin: base, GPU, session libraries, health. The desktop is COSMIC
# with the assistant as a layer-shell surface above it (ADR-0018); that stage does
# not exist yet, so this file still builds the platform and nothing above it. See
# docs/architecture/fedora-bootc.md §2.
#
# The base is pinned by digest (the multi-arch index digest). `dnf upgrade`
# still floats within Fedora 45; pinning that snapshot to a date is a Phase 0
# open question and is not pretended otherwise here.
#
# Re-pinned 2026-11-11: quay.io garbage-collects manifests that no tag
# references, and Fedora re-tags `45` at point releases — the original pin
# (sha256:0b34d5a...) stopped resolving and CI failed with "not found". A
# digest pin on quay is a lease, not an anchor; verify it when a build fails.

ARG BASE_IMAGE=quay.io/fedora/fedora-bootc:45@sha256:32efabff97ea5062b9c1f20fafc519038f6165017a140cb6c3b96469ba69a86e

FROM ${BASE_IMAGE}

ARG BUILD_ID=dev
ARG SOURCE_COMMIT=unknown

LABEL org.opencontainers.image.title="AI_OS" \
      org.opencontainers.image.description="Assistant-first operating system: platform image" \
      org.opencontainers.image.revision="${SOURCE_COMMIT}" \
      aios.build.id="${BUILD_ID}" \
      aios.build.source_commit="${SOURCE_COMMIT}" \
      aios.layer="platform"

# Layer 2 — GPU.
#
# The module is built in this image, against this image's kernel, so a
# kernel/module mismatch cannot occur at runtime. Verified against this exact
# base on 2026-11-10: the image ships kernel 7.2.15 while updates carry 7.3.3,
# and installing kernel-devel-matched upgrades the kernel. The script reads the
# kernel version *after* the upgrade; doing it the other way round fails with
# "Could not find files needed to compile modules".
#
# STRIP=1 removes akmods, the kernel-devel packages and gcc after the build. The
# installed kmod survives (verified), which is why this can be one stage.
COPY ci/build-nvidia-kmod.sh /usr/local/libexec/aios/build-nvidia-kmod.sh
RUN STRIP=1 bash /usr/local/libexec/aios/build-nvidia-kmod.sh \
 && rm -f /usr/local/libexec/aios/build-nvidia-kmod.sh

# Layer 3 — session runtime.
#
# Libraries only. COSMIC owns the rest (ADR-0018), and it arrives as one stage of
# its own so the desktop can be replaced atomically like everything else.
RUN dnf install -y --setopt=install_weak_deps=False \
      libwayland-server libwayland-client libwayland-egl libwayland-cursor \
      mesa-libEGL mesa-libgbm mesa-dri-drivers mesa-vulkan-drivers vulkan-loader \
      pipewire wireplumber xdg-desktop-portal \
      fontconfig google-noto-sans-vf-fonts \
 && dnf clean all

# Layer 6 — health.
#
# greenboot is NOT in the base image (verified 2026-11-10), despite the
# assumption in the architecture docs. Installing it is a real change, not a
# formality.
RUN dnf install -y --setopt=install_weak_deps=False greenboot \
 && dnf clean all

# The package installs its check runner disabled. Observed on a freshly installed
# system on 2026-11-11: `systemctl is-enabled greenboot-healthcheck.service`
# answers `disabled`, and its preset is disabled too, so nothing would run the
# checks and nothing would roll back. The rollback that ADR-0016 and the checks in
# image/greenboot/check assume is only real if this is enabled in the image.
RUN systemctl enable greenboot-healthcheck.service

# The stock timer ships enabled, runs daily, and reboots. Combined with greenboot
# rollback it re-applies the digest that was just rolled back from, producing a
# boot loop (ADR-0016 §5). aios-updated owns the cadence instead.
RUN systemctl mask bootc-fetch-apply-updates.timer

COPY image/greenboot/check/ /etc/greenboot/check/
RUN chmod 0755 /etc/greenboot/check/required.d/*.sh /etc/greenboot/check/wanted.d/*.sh

# Readable build identity. The same value is an OCI label above; the file exists
# so the running system, greenboot and support can read it without asking a
# registry. The release version is deliberately absent: it is assigned at
# promotion and lives only in the channel file (ADR-0015 §6).
RUN mkdir -p /usr/lib/aios \
 && printf '%s\n' "${BUILD_ID}" > /usr/lib/aios/build-id

# Fedora 45 keeps its default repository definitions in /usr/share/dnf5/repos.d,
# and dnf5 reads them from there. osbuild, which turns this image into an
# installer ISO, reads only /etc/yum.repos.d and therefore finds no repositories
# at all ("NoReposError: There are no enabled repositories"). Copying the files
# where osbuild looks changes nothing for dnf5, which reads both locations.
RUN if [ -d /usr/share/dnf5/repos.d ]; then \
      mkdir -p /etc/yum.repos.d \
      && cp -n /usr/share/dnf5/repos.d/*.repo /etc/yum.repos.d/; \
    fi
