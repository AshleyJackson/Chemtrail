from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aios_release import cli, demo, evidence
from aios_release.manifest import ChannelManifest
from aios_release.signing import DevHmacSigner
from tests.release.factories import BASE, boots, build, digest


class CliTests(unittest.TestCase):
    def setUp(self):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name)
        self.channels = self.root / "channels"
        self.channels.mkdir()
        self.evidence_dir = self.root / "evidence"
        self.evidence_dir.mkdir()

    def run_cli(self, argv, env=None):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            with patch.dict(os.environ, env or {}, clear=False):
                code = cli.main(argv)
        return code, out.getvalue(), err.getvalue()

    def seed_nightly_evidence(self, sha):
        from tests.release.factories import image

        evidence.write(build(sha, BASE), self.evidence_dir)
        evidence.write(image(sha, BASE), self.evidence_dir)
        for record in boots(sha, BASE, count=5):
            evidence.write(record, self.evidence_dir)

    def promote_nightly(self, sha, extra_env=None):
        return self.run_cli(
            [
                "promote",
                "--channel", "nightly",
                "--candidate", sha,
                "--channels", str(self.channels),
                "--evidence-dir", str(self.evidence_dir),
                "--out", str(self.channels / "nightly.json"),
                "--sign", "hmac:AIOS_TEST_KEY",
                "--now", "2026-11-02T00:00:00Z",
            ],
            env={"AIOS_TEST_KEY": "test-secret", **(extra_env or {})},
        )

    def test_demo_writes_four_valid_signed_channels(self):
        out_dir = self.root / "demo"
        code, output, error = self.run_cli(
            ["demo", "--out", str(out_dir), "--now", "2026-12-01T12:00:00Z"]
        )
        self.assertEqual(code, 0, error)
        self.assertIn("final pointers", output)
        signer = DevHmacSigner(demo.DEMO_KEY, key_id="demo")
        for channel in ("nightly", "weekly", "stable"):
            manifest = ChannelManifest.load(out_dir / "channels" / f"{channel}.json")
            self.assertEqual(manifest.channel, channel)
            self.assertTrue(signer.verify(manifest.payload(), manifest.signature), channel)
        stable = ChannelManifest.load(out_dir / "channels" / "stable.json")
        self.assertEqual(stable.version, "1.0.0")
        self.assertEqual(stable.rollout.percentage, 100)
        self.assertIn("5% rollout", output)

    def test_promote_then_verify(self):
        sha = digest("a")
        self.seed_nightly_evidence(sha)
        code, _, error = self.promote_nightly(sha)
        self.assertEqual(code, 0, error)
        path = self.channels / "nightly.json"
        manifest = ChannelManifest.load(path)
        self.assertTrue(manifest.signature)
        self.assertEqual(manifest.digest, sha)

        code, output, error = self.run_cli(
            ["verify", "--manifest", str(path), "--hmac-key-env", "AIOS_TEST_KEY"],
            env={"AIOS_TEST_KEY": "test-secret"},
        )
        self.assertEqual(code, 0, error)
        self.assertIn("signature valid", output)

    def test_verify_rejects_tampering(self):
        sha = digest("a")
        self.seed_nightly_evidence(sha)
        self.assertEqual(self.promote_nightly(sha)[0], 0)
        path = self.channels / "nightly.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        document["digest"] = digest("b")
        path.write_text(json.dumps(document), encoding="utf-8")

        code, _, error = self.run_cli(
            ["verify", "--manifest", str(path), "--hmac-key-env", "AIOS_TEST_KEY"],
            env={"AIOS_TEST_KEY": "test-secret"},
        )
        self.assertEqual(code, 1)
        self.assertIn("signature does not match", error)

    def test_unsigned_promotion_is_allowed_only_on_request_and_then_fails_verification(self):
        sha = digest("a")
        self.seed_nightly_evidence(sha)
        argv = [
            "promote",
            "--channel", "nightly",
            "--candidate", sha,
            "--channels", str(self.channels),
            "--evidence-dir", str(self.evidence_dir),
            "--out", str(self.channels / "nightly.json"),
            "--unsigned",
        ]
        self.assertEqual(self.run_cli(argv)[0], 0)
        path = self.channels / "nightly.json"
        self.assertEqual(ChannelManifest.load(path).signature, "")
        code, _, _ = self.run_cli(
            ["verify", "--manifest", str(path), "--hmac-key-env", "AIOS_TEST_KEY"],
            env={"AIOS_TEST_KEY": "test-secret"},
        )
        self.assertEqual(code, 1)

    def test_promotion_requires_an_explicit_signing_choice(self):
        sha = digest("a")
        self.seed_nightly_evidence(sha)
        code, _, error = self.run_cli([
            "promote",
            "--channel", "nightly",
            "--candidate", sha,
            "--channels", str(self.channels),
            "--evidence-dir", str(self.evidence_dir),
            "--out", str(self.channels / "nightly.json"),
        ])
        self.assertEqual(code, 1)
        self.assertIn("--sign", error)

    def test_plan_reports_failure_without_writing(self):
        sha = digest("a")
        self.seed_nightly_evidence(sha)
        code, output, _ = self.run_cli([
            "plan",
            "--channel", "weekly",
            "--candidate", sha,
            "--channels", str(self.channels),
            "--evidence-dir", str(self.evidence_dir),
            "--now", "2026-11-02T00:00:00Z",
        ])
        self.assertEqual(code, 1)
        self.assertIn("FAIL", output)
        self.assertIn("entered-nightly", output)
        self.assertFalse((self.channels / "weekly.json").exists())

    def test_select_prints_the_digest_ready_to_promote(self):
        sha = digest("a")
        self.seed_nightly_evidence(sha)
        code, output, _ = self.run_cli([
            "select",
            "--channel", "nightly",
            "--channels", str(self.channels),
            "--evidence-dir", str(self.evidence_dir),
            "--now", "2026-11-02T00:00:00Z",
        ])
        self.assertEqual(code, 0)
        self.assertEqual(output.strip(), sha)

    def test_select_fails_when_nothing_is_eligible(self):
        sha = digest("a")
        evidence.write(build(sha, BASE), self.evidence_dir)  # no boot
        code, _, error = self.run_cli([
            "select",
            "--channel", "nightly",
            "--channels", str(self.channels),
            "--evidence-dir", str(self.evidence_dir),
            "--now", "2026-11-02T00:00:00Z",
        ])
        self.assertEqual(code, 1)
        self.assertIn("nothing eligible", error)

    def test_resolve_command_answers_in_json(self):
        sha = digest("a")
        self.seed_nightly_evidence(sha)
        self.assertEqual(self.promote_nightly(sha)[0], 0)
        code, output, error = self.run_cli([
            "resolve",
            "--manifest", str(self.channels / "nightly.json"),
            "--running-digest", digest("b"),
            "--machine-id", "machine-1",
            "--json",
        ])
        self.assertEqual(code, 0, error)
        decision = json.loads(output)
        self.assertEqual(decision["action"], "update")
        self.assertEqual(decision["reason"], "candidate-newer")

    def seed_stable_evidence(self, sha):
        from datetime import timedelta

        from tests.release.factories import hardware, image, promotion

        evidence.write(build(sha, BASE), self.evidence_dir)
        evidence.write(image(sha, BASE), self.evidence_dir)
        for record in boots(sha, BASE, count=5):
            evidence.write(record, self.evidence_dir)
        evidence.write(promotion(sha, "nightly", BASE), self.evidence_dir)
        evidence.write(promotion(sha, "weekly", BASE + timedelta(days=1)), self.evidence_dir)
        evidence.write(hardware(sha, BASE + timedelta(hours=2)), self.evidence_dir)

    def test_withdraw_command_restores_the_previous_manifest(self):
        bad = digest("a")
        good = digest("b")
        self.seed_stable_evidence(bad)
        code, _, error = self.run_cli([
            "promote",
            "--channel", "stable",
            "--candidate", bad,
            "--channels", str(self.channels),
            "--evidence-dir", str(self.evidence_dir),
            "--out", str(self.channels / "stable.json"),
            "--sign", "hmac:AIOS_TEST_KEY",
            "--now", "2026-11-10T00:00:00Z",
        ], env={"AIOS_TEST_KEY": "test-secret"})
        self.assertEqual(code, 0, error)

        previous = self.channels / "stable.json"
        target = self.root / "previous.json"
        document = json.loads(previous.read_text(encoding="utf-8"))
        document["digest"] = good
        document["version"] = "0.9.0"
        document["release"] = "v0.9.0"
        document["signature"] = ""
        target.write_text(json.dumps(document), encoding="utf-8")

        code, _, error = self.run_cli([
            "withdraw",
            "--channel", "stable",
            "--channels", str(self.channels),
            "--target-manifest", str(target),
            "--out", str(self.channels / "stable.json"),
            "--sign", "hmac:AIOS_TEST_KEY",
            "--now", "2026-11-11T00:00:00Z",
        ], env={"AIOS_TEST_KEY": "test-secret"})
        self.assertEqual(code, 0, error)
        result = ChannelManifest.load(self.channels / "stable.json")
        self.assertEqual(result.digest, good)
        self.assertEqual(result.version, "1.0.1")
        self.assertEqual(result.release, "v1.0.1")
        self.assertIn(bad, result.supersedes)

    def test_withdraw_command_refuses_nightly(self):
        bad = digest("a")
        self.seed_nightly_evidence(bad)
        self.assertEqual(self.promote_nightly(bad)[0], 0)
        target = self.root / "previous.json"
        document = json.loads((self.channels / "nightly.json").read_text(encoding="utf-8"))
        document["digest"] = digest("b")
        document["signature"] = ""
        target.write_text(json.dumps(document), encoding="utf-8")
        code, _, error = self.run_cli([
            "withdraw",
            "--channel", "nightly",
            "--channels", str(self.channels),
            "--target-manifest", str(target),
            "--out", str(self.channels / "nightly.json"),
            "--sign", "hmac:AIOS_TEST_KEY",
            "--now", "2026-11-03T00:00:00Z",
        ], env={"AIOS_TEST_KEY": "test-secret"})
        self.assertEqual(code, 1)
        self.assertIn("nothing to withdraw", error)
