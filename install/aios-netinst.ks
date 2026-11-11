# Network install kickstart (ADR-0020, ADR-0021). Render per channel with a
# promoted digest. Storage, the account and the network are answered in the
# graphical installer; autopart, rootpw or user here would answer them instead and
# there would be nothing left to ask.
lang en_US.UTF-8
keyboard us
timezone UTC --utc
graphical
xconfig --startxonboot
bootc --source-imgref=registry:ghcr.io/ashleyjackson/chemtrail@sha256:74c6ed2a0a1b38775527457b5265e44c45250e0faac18c6563ab1253b773482c --target-imgref=ghcr.io/ashleyjackson/chemtrail@sha256:74c6ed2a0a1b38775527457b5265e44c45250e0faac18c6563ab1253b773482c
