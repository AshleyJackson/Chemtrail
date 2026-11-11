# Network install kickstart (ADR-0020, ADR-0021). Render per channel with a
# promoted digest. Storage, the account and the network are answered in the
# graphical installer; autopart, rootpw or user here would answer them instead and
# there would be nothing left to ask.
lang en_US.UTF-8
keyboard us
timezone UTC --utc
graphical
xconfig --startxonboot
bootc --source-imgref=registry:ghcr.io/ashleyjackson/chemtrail@sha256:8f1fa6ab22bf63f55d5a5f985daabff825224392f606740a8b690fc9c3d0d6df --target-imgref=ghcr.io/ashleyjackson/chemtrail@sha256:8f1fa6ab22bf63f55d5a5f985daabff825224392f606740a8b690fc9c3d0d6df
