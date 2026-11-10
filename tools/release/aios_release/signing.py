"""Signing, deliberately as a thin seam.

Production uses sigstore ``cosign`` with a key held outside the runner. The
promotion core never holds a signing key, never shells out, and never decides
which algorithm is acceptable: it produces the canonical payload, and the caller
supplies a signature.

Two signers exist here:

* :class:`DevHmacSigner` — a local stub so the pipeline can be exercised and
  tested end to end. It is symmetric, which is wrong for a public product: a
  device holding the verification key could also sign. It must never ship.
* :class:`UnsignedSigner` — writes an empty signature, so CI can attach a real
  one with ``attach-signature``. ``promote`` refuses to write an unsigned file
  unless this is chosen explicitly.

The client trusts a public key baked into the image, not GitHub's identity and
not an algorithm named inside the file. Letting the document choose its own
algorithm is how signature verification bugs become vulnerabilities.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
from dataclasses import dataclass
from typing import Protocol

from .manifest import ChannelManifest, ManifestError


class Signer(Protocol):
    name: str

    def sign(self, payload: bytes) -> str: ...

    def verify(self, payload: bytes, signature: str) -> bool: ...


@dataclass(frozen=True)
class DevHmacSigner:
    """Local development stub. Symmetric, therefore not a shipping design."""

    secret: bytes
    key_id: str = "dev"
    name_suffix: str = "hmac-sha256"

    @property
    def name(self) -> str:
        return f"{self.name_suffix}:{self.key_id}"

    def sign(self, payload: bytes) -> str:
        digest = hmac.new(self.secret, payload, hashlib.sha256).digest()
        return base64.b64encode(digest).decode("ascii")

    def verify(self, payload: bytes, signature: str) -> bool:
        try:
            expected = self.sign(payload)
        except (ValueError, TypeError):
            return False
        return hmac.compare_digest(expected, signature)


@dataclass(frozen=True)
class UnsignedSigner:
    name: str = "unsigned"

    def sign(self, payload: bytes) -> str:
        return ""

    def verify(self, payload: bytes, signature: str) -> bool:
        return False


def signer_from_spec(spec: str) -> Signer:
    """``hmac:<ENV_VAR>`` for the dev stub, ``none`` for an explicit unsigned run."""
    if spec in ("none", "unsigned"):
        return UnsignedSigner()
    if spec.startswith("hmac:"):
        variable = spec.split(":", 1)[1]
        secret = os.environ.get(variable)
        if not secret:
            raise ManifestError(f"signing key environment variable {variable} is empty or unset")
        return DevHmacSigner(secret.encode("utf-8"), key_id=variable)
    raise ManifestError(f"unknown signer spec {spec!r}; expected 'hmac:<ENV_VAR>' or 'none'")


def sign_manifest(manifest: ChannelManifest, signer: Signer) -> ChannelManifest:
    return manifest.with_signature(signer.sign(manifest.payload()))


def verify_manifest(manifest: ChannelManifest, signer: Signer) -> ChannelManifest:
    if not signer.verify(manifest.payload(), manifest.signature):
        raise ManifestError("signature does not match the channel file")
    return manifest
