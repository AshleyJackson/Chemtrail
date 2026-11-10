from __future__ import annotations

import base64
import os
import unittest
from dataclasses import replace
from unittest.mock import patch

from aios_release.manifest import ManifestError
from aios_release.signing import (
    DevHmacSigner,
    UnsignedSigner,
    sign_manifest,
    signer_from_spec,
    verify_manifest,
)
from tests.release.factories import BASE, digest, manifest

SIGNER = DevHmacSigner(b"secret", key_id="test")


def signed():
    return sign_manifest(manifest("stable", digest("a"), BASE, version="1.0.0"), SIGNER)


class DevHmacSignerTests(unittest.TestCase):
    def test_round_trip(self):
        payload = b"hello"
        self.assertTrue(SIGNER.verify(payload, SIGNER.sign(payload)))

    def test_tampered_payload_fails(self):
        signature = SIGNER.sign(b"hello")
        self.assertFalse(SIGNER.verify(b"hello!", signature))

    def test_another_secret_fails(self):
        signature = DevHmacSigner(b"other").sign(b"hello")
        self.assertFalse(SIGNER.verify(b"hello", signature))

    def test_empty_signature_fails(self):
        self.assertFalse(SIGNER.verify(b"hello", ""))

    def test_signature_is_deterministic(self):
        self.assertEqual(SIGNER.sign(b"x"), SIGNER.sign(b"x"))

    def test_signature_is_a_full_length_digest(self):
        self.assertEqual(len(base64.b64decode(SIGNER.sign(b"x"))), 32)

    def test_name_names_the_key(self):
        self.assertEqual(SIGNER.name, "hmac-sha256:test")


class UnsignedSignerTests(unittest.TestCase):
    def test_signs_to_nothing(self):
        self.assertEqual(UnsignedSigner().sign(b"x"), "")

    def test_never_verifies(self):
        self.assertFalse(UnsignedSigner().verify(b"x", ""))

    def test_name(self):
        self.assertEqual(UnsignedSigner().name, "unsigned")


class SignerFactoryTests(unittest.TestCase):
    def test_none_is_unsigned(self):
        self.assertIsInstance(signer_from_spec("none"), UnsignedSigner)
        self.assertIsInstance(signer_from_spec("unsigned"), UnsignedSigner)

    def test_hmac_reads_the_named_environment_variable(self):
        with patch.dict(os.environ, {"MY_KEY": "sekrit"}):
            signer = signer_from_spec("hmac:MY_KEY")
        self.assertIsInstance(signer, DevHmacSigner)
        self.assertEqual(signer.secret, b"sekrit")
        self.assertEqual(signer.name, "hmac-sha256:MY_KEY")

    def test_unset_variable_is_refused(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ManifestError):
                signer_from_spec("hmac:NOPE")

    def test_empty_variable_is_refused(self):
        with patch.dict(os.environ, {"EMPTY": ""}):
            with self.assertRaises(ManifestError):
                signer_from_spec("hmac:EMPTY")

    def test_unknown_spec_is_refused(self):
        with self.assertRaises(ManifestError):
            signer_from_spec("gpg:whatever")


class ManifestSigningTests(unittest.TestCase):
    def test_a_freshly_signed_manifest_verifies(self):
        signed_manifest = signed()
        self.assertEqual(verify_manifest(signed_manifest, SIGNER), signed_manifest)

    def test_verification_fails_after_a_field_changes(self):
        tampered = replace(signed(), digest=digest("b"))
        with self.assertRaises(ManifestError) as caught:
            verify_manifest(tampered, SIGNER)
        self.assertIn("signature", str(caught.exception))

    def test_an_unsigned_manifest_fails(self):
        with self.assertRaises(ManifestError):
            verify_manifest(manifest("stable", digest("a"), BASE, version="1.0.0"), SIGNER)

    def test_verification_fails_for_the_wrong_key(self):
        with self.assertRaises(ManifestError):
            verify_manifest(signed(), DevHmacSigner(b"different", key_id="test"))

    def test_re_signing_a_changed_manifest_verifies_again(self):
        changed = sign_manifest(replace(signed(), digest=digest("b")), SIGNER)
        self.assertEqual(verify_manifest(changed, SIGNER), changed)
