# Network install kickstart (ADR-0020). Render per channel with a promoted digest.
# Validated against pykickstart 3.77-1.fc45, the parser on Fedora 45 netinst media.
#
# Deliberately incomplete: Anaconda 45 has no interactive kickstart command, so a
# kickstart cannot ask questions. Leaving storage, the account and the network
# unanswered hands them to the installer UI, which collects them and writes them
# into the deployment. Do not add autopart, rootpw or user here.
lang en_US.UTF-8
keyboard us
timezone UTC --utc
xconfig --startxonboot
bootc --source-imgref=registry:ghcr.io/ashleyjackson/chemtrail@sha256:867ac8ba662e4ed63e85eb9abae88b863f4fc072f919058f3a94e60d4e0f11a8 --target-imgref=ghcr.io/ashleyjackson/chemtrail@sha256:867ac8ba662e4ed63e85eb9abae88b863f4fc072f919058f3a94e60d4e0f11a8
