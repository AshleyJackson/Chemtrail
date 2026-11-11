# syntax=docker/dockerfile:1

# AI_OS platform image: base, GPU, session runtime, desktop, health.

ARG BASE_IMAGE=quay.io/fedora/fedora-bootc:45@sha256:32efabff97ea5062b9c1f20fafc519038f6165017a140cb6c3b96469ba69a86e

FROM ${BASE_IMAGE}

ARG BUILD_ID=dev
ARG SOURCE_COMMIT=unknown

LABEL org.opencontainers.image.title="AI_OS" \
      org.opencontainers.image.description="Assistant-first operating system: platform image" \
      org.opencontainers.image.revision="${SOURCE_COMMIT}" \
      aios.build.id="${BUILD_ID}" \
      aios.build.source_commit="${SOURCE_COMMIT}" \
      aios.layer="desktop"

# Built against this image's kernel; STRIP=1 removes the toolchain afterwards.
COPY ci/build-nvidia-kmod.sh /usr/local/libexec/aios/build-nvidia-kmod.sh
RUN STRIP=1 bash /usr/local/libexec/aios/build-nvidia-kmod.sh \
 && rm -f /usr/local/libexec/aios/build-nvidia-kmod.sh

RUN dnf install -y --setopt=install_weak_deps=False \
      libwayland-server libwayland-client libwayland-egl libwayland-cursor \
      mesa-libEGL mesa-libgbm mesa-dri-drivers mesa-vulkan-drivers vulkan-loader \
      pipewire wireplumber xdg-desktop-portal \
      fontconfig google-noto-sans-vf-fonts \
 && dnf clean all

# Desktop (ADR-0018).
RUN dnf install -y --setopt=install_weak_deps=False \
      @cosmic-desktop cosmic-greeter cosmic-greeter-daemon \
 && dnf clean all

# cosmic-greeter.service is the display manager and is enabled by preset; its
# D-Bus daemon is not, and the greeter cannot log anyone in without it.
RUN systemctl enable cosmic-greeter-daemon.service \
 && systemctl set-default graphical.target

RUN dnf install -y --setopt=install_weak_deps=False greenboot \
 && dnf clean all

# The package ships the check runner disabled.
RUN systemctl enable greenboot-healthcheck.service

# The stock timer reboots on its own; aios-updated owns the cadence (ADR-0016).
RUN systemctl mask bootc-fetch-apply-updates.timer

COPY image/greenboot/check/ /etc/greenboot/check/
RUN chmod 0755 /etc/greenboot/check/required.d/*.sh /etc/greenboot/check/wanted.d/*.sh

RUN mkdir -p /usr/lib/aios \
 && printf '%s\n' "${BUILD_ID}" > /usr/lib/aios/build-id

# osbuild reads only /etc/yum.repos.d; Fedora 45 keeps the defaults in
# /usr/share/dnf5/repos.d, and dnf5 reads both.
RUN if [ -d /usr/share/dnf5/repos.d ]; then \
      mkdir -p /etc/yum.repos.d \
      && cp -n /usr/share/dnf5/repos.d/*.repo /etc/yum.repos.d/; \
    fi
