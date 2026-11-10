from __future__ import annotations

import unittest

from aios_release.canonical import SIGNATURE_FIELD, canonical_bytes


class CanonicalBytesTests(unittest.TestCase):
    def test_keys_are_sorted(self):
        self.assertEqual(canonical_bytes({"b": 1, "a": 2}), b'{"a":2,"b":1}')

    def test_signature_is_omitted_by_default(self):
        payload = canonical_bytes({"a": 1, SIGNATURE_FIELD: "abc"})
        self.assertEqual(payload, b'{"a":1}')
        self.assertNotIn(b"signature", payload)

    def test_omission_can_be_extended(self):
        self.assertEqual(canonical_bytes({"a": 1, "b": 2}, omit=("a", "b")), b"{}")

    def test_nested_keys_are_sorted(self):
        self.assertEqual(canonical_bytes({"outer": {"z": 1, "a": 2}}), b'{"outer":{"a":2,"z":1}}')

    def test_unicode_survives_as_utf8(self):
        self.assertEqual(canonical_bytes({"note": "café"}), '{"note":"café"}'.encode("utf-8"))

    def test_no_insignificant_whitespace(self):
        payload = canonical_bytes({"a": [1, 2], "b": {"c": 3}})
        self.assertEqual(payload, b'{"a":[1,2],"b":{"c":3}}')
        self.assertNotIn(b" ", payload)
        self.assertNotIn(b"\n", payload)

    def test_nan_is_refused_rather_than_written(self):
        # NaN is not JSON. Failing here beats emitting a payload that two parsers
        # disagree about, which would make a signature unverifiable.
        with self.assertRaises(ValueError):
            canonical_bytes({"value": float("nan")})

    def test_empty_document(self):
        self.assertEqual(canonical_bytes({}), b"{}")

    def test_insertion_order_does_not_matter(self):
        first = {"a": 1, "b": 2, "c": 3}
        second = {"c": 3, "b": 2, "a": 1}
        self.assertEqual(canonical_bytes(first), canonical_bytes(second))
