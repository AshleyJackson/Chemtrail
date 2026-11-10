from __future__ import annotations

import contextlib
import io
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from aios_release import demo
from aios_release.manifest import ChannelManifest
from aios_release.signing import DevHmacSigner, verify_manifest

NOW = datetime(2026, 11, 22, 9, 0, 0, tzinfo=timezone.utc)


def run(out: Path) -> str:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        demo.run(out, now=NOW)
    return buffer.getvalue()


class DemoTests(unittest.TestCase):
    def test_writes_one_channel_file_per_channel(self):
        with TemporaryDirectory() as directory:
            out = Path(directory)
            run(out)
            for channel in ("nightly", "weekly", "stable"):
                manifest = ChannelManifest.load(out / "channels" / f"{channel}.json")
                self.assertEqual(manifest.channel, channel)

    def test_stable_ends_at_version_one_and_full_rollout(self):
        with TemporaryDirectory() as directory:
            out = Path(directory)
            run(out)
            stable = ChannelManifest.load(out / "channels" / "stable.json")
            self.assertEqual(stable.version, "1.0.0")
            self.assertEqual(stable.rollout.percentage, 100)

    def test_nightly_tracks_the_newest_build(self):
        with TemporaryDirectory() as directory:
            out = Path(directory)
            run(out)
            self.assertEqual(ChannelManifest.load(out / "channels" / "nightly.json").digest, demo.digest_for("D"))

    def test_every_channel_file_verifies_against_the_demo_key(self):
        signer = DevHmacSigner(demo.DEMO_KEY, key_id="demo")
        with TemporaryDirectory() as directory:
            out = Path(directory)
            run(out)
            for channel in ("nightly", "weekly", "stable"):
                manifest = ChannelManifest.load(out / "channels" / f"{channel}.json")
                self.assertEqual(verify_manifest(manifest, signer), manifest)

    def test_the_same_inputs_produce_byte_identical_files(self):
        with TemporaryDirectory() as first, TemporaryDirectory() as second:
            run(Path(first))
            run(Path(second))
            for channel in ("nightly", "weekly", "stable"):
                one = (Path(first) / "channels" / f"{channel}.json").read_bytes()
                two = (Path(second) / "channels" / f"{channel}.json").read_bytes()
                self.assertEqual(one, two, channel)

    def test_the_summary_reports_rollout_eligibility_without_telemetry(self):
        with TemporaryDirectory() as directory:
            output = run(Path(directory))
        self.assertIn("eligible", output)
        self.assertIn("deterministically", output)
        self.assertIn("final pointers", output)

    def test_demo_digests_are_real_sha256_values(self):
        self.assertTrue(demo.digest_for("A").startswith("sha256:"))
        self.assertEqual(len(demo.digest_for("A")), len("sha256:") + 64)
