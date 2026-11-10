from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from aios_release.canonical import canonical_bytes
from aios_release.manifest import (
    ChannelManifest,
    ManifestError,
    Rollout,
    parse_version,
    problems,
    validate,
)
from tests.release.factories import BASE, digest, manifest


class CanonicalTests(unittest.TestCase):
    def test_signature_is_excluded_from_the_signed_payload(self):
        unsigned = manifest("stable", digest("a"), BASE, version="1.0.0")
        signed = unsigned.with_signature("whatever")
        self.assertEqual(canonical_bytes(unsigned.to_dict()), canonical_bytes(signed.to_dict()))
        self.assertNotIn(b"signature", canonical_bytes(signed.to_dict()))

    def test_key_order_does_not_change_the_payload(self):
        document = manifest("stable", digest("a"), BASE, version="1.0.0").to_dict()
        reordered = dict(reversed(list(document.items())))
        self.assertEqual(canonical_bytes(document), canonical_bytes(reordered))

    def test_payload_has_no_insignificant_whitespace(self):
        payload = manifest("stable", digest("a"), BASE, version="1.0.0").payload()
        self.assertNotIn(b": ", payload)
        self.assertNotIn(b"\n", payload)


class ValidationTests(unittest.TestCase):
    def test_valid_stable_manifest(self):
        validate(manifest("stable", digest("a"), BASE, version="1.0.0"))
        self.assertEqual(problems(manifest("stable", digest("a"), BASE, version="1.0.0")), [])

    def test_stable_requires_a_version(self):
        found = problems(manifest("stable", digest("a"), BASE))
        self.assertTrue(any("requires a version" in item for item in found), found)

    def test_nightly_must_not_carry_a_version(self):
        found = problems(manifest("nightly", digest("a"), BASE, version="1.0.0"))
        self.assertTrue(any("no version or release" in item for item in found), found)

    def test_release_must_match_version(self):
        bad = replace(
            manifest("stable", digest("a"), BASE, version="1.0.0"),
            release="v1.0.1",
        )
        self.assertTrue(any("'v' + version" in item for item in problems(bad)))

    def test_rejects_own_digest_in_supersedes(self):
        bad = manifest("stable", digest("a"), BASE, version="1.0.0", supersedes=(digest("a"),))
        self.assertTrue(any("points at" in item for item in problems(bad)))

    def test_rejects_duplicate_supersedes(self):
        bad = manifest(
            "stable", digest("a"), BASE, version="1.0.0",
            supersedes=(digest("b"), digest("b")),
        )
        self.assertTrue(any("duplicates" in item for item in problems(bad)))

    def test_rejects_oversized_supersedes(self):
        chain = tuple(f"sha256:{index:064x}" for index in range(17))
        bad = manifest("stable", digest("a"), BASE, version="1.0.0", supersedes=chain)
        self.assertTrue(any("cap is" in item for item in problems(bad)))

    def test_rollout_needs_a_seed_and_a_start(self):
        bad = manifest(
            "stable", digest("a"), BASE, version="1.0.0",
            rollout=Rollout(percentage=5, seed="", started=""),
        )
        found = problems(bad)
        self.assertTrue(any("rollout.seed" in item for item in found), found)
        self.assertTrue(any("rollout.started" in item for item in found), found)

    def test_rollout_percentage_is_bounded(self):
        bad = manifest(
            "stable", digest("a"), BASE, version="1.0.0",
            rollout=Rollout(percentage=101, seed="s", started="2026-11-01T00:00:00Z"),
        )
        self.assertTrue(any("0-100" in item for item in problems(bad)))

    def test_rollout_rejects_float_percentage(self):
        bad = manifest(
            "stable", digest("a"), BASE, version="1.0.0",
            rollout=Rollout(percentage=5.5, seed="s", started="2026-11-01T00:00:00Z"),  # type: ignore[arg-type]
        )
        self.assertTrue(any("integer" in item for item in problems(bad)))

    def test_digest_must_be_sha256_hex(self):
        bad = manifest("stable", "sha256:nothex", BASE, version="1.0.0")
        self.assertTrue(any("digest must be" in item for item in problems(bad)))

    def test_signature_can_be_required(self):
        with self.assertRaises(ManifestError):
            validate(manifest("stable", digest("a"), BASE, version="1.0.0"), require_signature=True)

    def test_parse_version_rejects_rubbish(self):
        with self.assertRaises(ManifestError):
            parse_version("1.0")
        self.assertEqual(parse_version("1.4.2"), (1, 4, 2))


class FileTests(unittest.TestCase):
    def test_dump_and_load_round_trip(self):
        original = manifest("stable", digest("a"), BASE, version="1.0.0").with_signature("sig")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "channels" / "stable.json"
            original.dump(path)
            self.assertEqual(ChannelManifest.load(path), original)
            document = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(list(document)[0], "schema")
            self.assertTrue(path.read_text(encoding="utf-8").endswith("\n"))
