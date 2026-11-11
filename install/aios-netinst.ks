# Network install kickstart (ADR-0020, ADR-0021). Render per channel with a
# promoted digest. Storage, the account and the network are answered in the
# graphical installer; autopart, rootpw or user here would answer them instead and
# there would be nothing left to ask.
lang en_US.UTF-8
keyboard us
timezone UTC --utc
graphical
xconfig --startxonboot
bootc --source-imgref=registry:ghcr.io/ashleyjackson/chemtrail@sha256:867ac8ba662e4ed63e85eb9abae88b863f4fc072f919058f3a94e60d4e0f11a8 --target-imgref=ghcr.io/ashleyjackson/chemtrail@sha256:867ac8ba662e4ed63e85eb9abae88b863f4fc072f919058f3a94e60d4e0f11a8
