# AI_OS network install kickstart (ADR-0020).
#
# Reviewed template for one-off installs: Fedora's own netinst media plus this
# file, passed to the installer as inst.ks=<url>. It wipes the disk and deploys
# exactly one image, pinned by digest - the digest is the identity (ADR-0015),
# so nothing here follows a tag. Promotion renders per-channel kickstarts with
# the promoted digests; this file is not what devices poll for updates.
#
# The pinned digest is the image CI published for commit 9219567
# (ghcr.io/ashleyjackson/chemtrail:sha-92195674d293b58a389e10cdb6b4cb5e5f53084b),
# the first publication to GHCR. It is a multi-arch index digest; the installer
# selects the amd64 child on x86_64 machines.
#
# Validated against pykickstart 3.77-1.fc45 from the Fedora 45 repositories -
# the parser Anaconda on F45 netinst media uses (see ADR-0020, Context).

zerombr
clearpart --all --initlabel
autopart
lang en_US.UTF-8
keyboard us
timezone UTC --utc
rootpw changeme
bootc --source-imgref=registry:ghcr.io/ashleyjackson/chemtrail@sha256:867ac8ba662e4ed63e85eb9abae88b863f4fc072f919058f3a94e60d4e0f11a8 --target-imgref=ghcr.io/ashleyjackson/chemtrail@sha256:867ac8ba662e4ed63e85eb9abae88b863f4fc072f919058f3a94e60d4e0f11a8
