# Network install kickstart (ADR-0020). Render per channel with a promoted digest.
# Validated against pykickstart 3.77-1.fc45, the parser on Fedora 45 netinst media.
# Digest below is the image published for commit 9219567.

zerombr
clearpart --all --initlabel
autopart
lang en_US.UTF-8
keyboard us
timezone UTC --utc
rootpw changeme
# Anaconda otherwise leaves default.target on multi-user.target, which shadows the
# image's graphical default and boots to a terminal with no getty and no greeter.
xconfig --startxonboot
bootc --source-imgref=registry:ghcr.io/ashleyjackson/chemtrail@sha256:867ac8ba662e4ed63e85eb9abae88b863f4fc072f919058f3a94e60d4e0f11a8 --target-imgref=ghcr.io/ashleyjackson/chemtrail@sha256:867ac8ba662e4ed63e85eb9abae88b863f4fc072f919058f3a94e60d4e0f11a8
